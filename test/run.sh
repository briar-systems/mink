#!/usr/bin/env bash
# the oracle lanes: mink judged from outside over the reference corpus. the roundtrip,
# readobj and neutral lanes run per registered format, so a format joins by registering and the
# harness never changes. they run locally and are never part of CI.
#
# usage: test/run.sh [--roundtrip] [--readobj] [--neutral] [--fuzz[=seconds]] [corpus]
#
#   --roundtrip  read each corpus file through its registered reader, write it
#                back through its writer and compare the bytes, unnormalised;
#                a difference is reported with the file, the first offset and the
#                model record that holds it
#   --readobj    compare every field mink dump and llvm-readobj both print. llvm-readobj
#                runs with --all --expand-relocs and the flags the format declares
#                (`mink reference <format>`), so a format's records join the comparison
#                by declaring them, never by a branch here
#   --neutral    convert each file to the neutral object, build its format's file from
#                that, read it and convert it again (`mink neutral`), and report a pair of
#                neutral objects that differ. every file answers its kind, and an object a
#                conversion refuses fails the lane. a file of another kind, a container
#                among them, is counted out of scope by its kind, and an object of a format
#                whose conversion is not built is counted apart. neither fails the lane
#   --fuzz       hostile input: mutate the seeds of test/fuzz/seeds and the corpus
#                files each reader claims, read every mutant in a child process
#                with a time and memory bound, and report a crash, a hang or a
#                read past the end as a finding with the saved input's path and
#                hash. a refusal is a pass. every reader the fuzz program lists
#                is run for the stated seconds, default 60, so a reader joins by
#                registering. findings are kept under the run's findings directory
#   corpus       the corpus directory, default $MINK_CORPUS, then
#                ~/.cache/mink-corpus (see test/corpus/README.md)
#   MINK         the program under test, default out/<host>/debug/bin/mink
#   READOBJ      the reference tool, default llvm-readobj
#
# the roundtrip and readobj lanes report a format with no registered reader as
# such and do not fail on it.
# a container's files are inputs of the lanes in their own right, reached through
# the container's registered member operations, so a member joins with no special case.
# a file no registered format claims is not part of the first two lanes.
#
# each lane owns out/oracle/<lane>. a run takes it with the lock out/oracle/<lane>/lock, a
# symlink naming the run's pid, made atomically and removed when the run exits. a lane whose
# lock is held is refused with the holder's pid, and a lock whose pid is not running is
# reported as stale for the user to remove. each lane of a run writes into a fresh directory
# out/oracle/<lane>/<time>.<suffix>, printed with the lane, and nothing is ever deleted, so
# lanes run at once never touch each other's files.
set -u

here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
repo=$(CDPATH= cd -- "$here/.." && pwd)

usage() { sed -n '2,/^[^#]/{/^#/p}' "$0" | sed 's/^# \{0,1\}//' >&2; exit 2; }

lanes=
add_lane() { case " $lanes " in *" $1 "*) ;; *) lanes="$lanes $1" ;; esac; }
fuzz_time=60
corpus=${MINK_CORPUS:-$HOME/.cache/mink-corpus}
while [ $# -gt 0 ]; do
    case "$1" in
        --roundtrip) add_lane roundtrip ;;
        --readobj)   add_lane readobj ;;
        --neutral)   add_lane neutral ;;
        --fuzz)      add_lane fuzz ;;
        --fuzz=*)    add_lane fuzz; fuzz_time=${1#--fuzz=} ;;
        -h|--help)   usage ;;
        -*) echo "run.sh: unknown option '$1'" >&2; usage ;;
        *)  corpus=$1 ;;
    esac
    shift
done
[ -n "$lanes" ] || usage

case "$(uname -s)/$(uname -m)" in
    Linux/x86_64)  host_dir=linux-x86_64 ;;
    Linux/aarch64) host_dir=linux-aarch64 ;;
    Darwin/arm64)  host_dir=darwin-aarch64 ;;
    Darwin/x86_64) host_dir=darwin-x86_64 ;;
    *) echo "run.sh: no mink build for this host" >&2; exit 2 ;;
esac
mink=${MINK:-$repo/out/$host_dir/debug/bin/mink}
readobj=${READOBJ:-llvm-readobj}
fuzz=${FUZZ:-$repo/out/$host_dir/debug/bin/fuzz}
[ -x "$mink" ] || { echo "run.sh: $mink is not built, run: mach build . -a cli" >&2; exit 2; }
[ -d "$corpus" ] || { echo "run.sh: corpus directory '$corpus' does not exist" >&2; exit 2; }

case "$lanes" in
    *fuzz*) [ -x "$fuzz" ] || { echo "run.sh: $fuzz is not built, run: mach build . -a fuzz" >&2; exit 2; } ;;
esac

oracle=$repo/out/oracle
locks=()

# remove only the locks this run made, and only while they still name this run
release_locks() {
    local lock
    for lock in ${locks[@]+"${locks[@]}"}; do
        [ "$(readlink "$lock" 2>/dev/null)" = "$$" ] && rm -f -- "$lock"
    done
}
trap release_locks EXIT
trap 'exit 129' HUP
trap 'exit 130' INT
trap 'exit 143' TERM

take_lock() {
    local dir=$oracle/$1 holder
    mkdir -p "$dir" || exit 2
    if ln -s "$$" "$dir/lock" 2>/dev/null; then
        locks+=("$dir/lock")
        return
    fi
    if ! holder=$(readlink "$dir/lock" 2>/dev/null); then
        echo "run.sh: the $1 lane's lock $dir/lock was released while it was read, run again" >&2
    elif ps -p "$holder" >/dev/null 2>&1; then
        echo "run.sh: the $1 lane is held by pid $holder ($dir/lock)" >&2
    else
        echo "run.sh: stale lock $dir/lock names pid $holder, which is not running, remove it to run the $1 lane" >&2
    fi
    exit 2
}

for lane in $lanes; do take_lock "$lane"; done

formats=$("$mink" formats) || exit 2
index=
failed=0

# index the corpus once per run, in the directory of the first lane that needs it:
# <format> <tab> <path> <tab> <label>, for the files a registered format claims and for
# the files the containers among them hold
build_index() {
    [ -n "$index" ] && return
    index=$work/index
    : > "$index"
    local n=0 f name dir list idx mname mfmt
    while IFS= read -r f; do
        name=$("$mink" sniff "$f" 2>/dev/null) || continue
        printf '%s\t%s\t%s\n' "$name" "$f" "$f" >> "$index"
        n=$((n + 1))
        dir=$work/members/$n
        mkdir -p "$dir"
        list=$("$mink" members "$f" -o "$dir" 2>/dev/null) || continue
        while IFS= read -r line; do
            [ -n "$line" ] || continue
            idx=${line%% *}
            mname=${line#* }
            mfmt=$("$mink" sniff "$dir/$idx" 2>/dev/null) || continue
            printf '%s\t%s\t%s(%s)\n' "$mfmt" "$dir/$idx" "$f" "$mname" >> "$index"
        done <<EOF2
$list
EOF2
    done < <(find "$corpus" -type f | sort)
}

lane_roundtrip() {
    local file=$1 label=$2 out=$work/roundtrip.bin err
    if ! err=$("$mink" roundtrip "$file" -o "$out" 2>&1); then
        echo "  $label: $err"
        return 1
    fi
    if ! cmp -s "$file" "$out"; then
        local at
        at=$(cmp "$file" "$out" 2>&1 | sed -n 's/.*byte \([0-9]*\).*/\1/p; s/.*EOF.*/end/p' | head -n 1)
        case "$at" in
            ''|end) echo "  $label: output differs in length" ;;
            *)
                local off where
                off=$(printf '0x%x' "$((at - 1))")
                where=$("$mink" locate "$file" "$off" 2>&1) || where="no record (${where#mink: })"
                printf '  %s: first difference at offset %s, in %s\n' "$label" "$off" "$where" ;;
        esac
        return 1
    fi
}

lane_readobj() {
    local file=$1 label=$2 ours=$work/mink.txt theirs=$work/readobj.txt err
    if ! err=$("$mink" dump "$file" 2>&1 >"$ours"); then
        echo "  $label: $err"
        return 1
    fi
    if ! "$readobj" --all --expand-relocs ${refflags[@]+"${refflags[@]}"} "$file" >"$theirs" 2>"$work/readobj.err"; then
        echo "  $label: $readobj refused the file: $(head -n 1 "$work/readobj.err")"
        return 1
    fi
    local diff
    if ! diff=$(python3 -I "$here/lib/crossread.py" "$ours" "$theirs"); then
        echo "  $label:"
        echo "$diff"
        return 1
    fi
}

lane_neutral() {
    local file=$1 label=$2 err rc
    err=$("$mink" neutral "$file" 2>&1)
    rc=$?
    [ "$rc" -eq 0 ] && return 0
    if [ "$rc" -eq 3 ] || [ "$rc" -eq 4 ]; then
        printf '%s\n' "${err#mink: }" | sed 's/^[^:]*: //; s/0x[0-9a-f]*/N/g; s/[0-9][0-9]*/N/g' >> "$work/scope$rc.txt"
        return "$rc"
    fi
    echo "  $label: $err"
    return 1
}

for lane in $lanes; do
    work=$(mktemp -d "$oracle/$lane/$(date +%Y%m%d-%H%M%S).XXXXXX") || exit 2
    echo "== $lane ($work)"
    if [ "$lane" = fuzz ]; then
        python3 -I "$here/lib/fuzz.py" --fuzz "$fuzz" --time "$fuzz_time" --out "$work/findings" \
            "$here/fuzz/seeds" "$corpus" || failed=1
        continue
    fi
    if [ "$lane" = readobj ] && ! command -v "$readobj" >/dev/null 2>&1; then
        echo "run.sh: $readobj not found" >&2
        exit 2
    fi
    while read -r name state; do
        if [ "$state" != registered ]; then
            echo "$name: no registered reader"
            continue
        fi
        build_index
        total=0
        held=0
        scoped=0
        unbuilt=0
        bad=0
        refflags=()
        if [ "$lane" = readobj ]; then
            refs=$("$mink" reference "$name") || { echo "run.sh: mink reference $name failed" >&2; exit 2; }
            if [ -n "$refs" ]; then
                while IFS= read -r flag; do refflags+=("$flag"); done <<EOF
$refs
EOF
            fi
        fi
        while IFS="$(printf '\t')" read -r fmt file label; do
            [ "$fmt" = "$name" ] || continue
            total=$((total + 1))
            [ "$file" = "$label" ] || held=$((held + 1))
            "lane_$lane" "$file" "$label"
            case $? in
                0) ;;
                3) scoped=$((scoped + 1)) ;;
                4) unbuilt=$((unbuilt + 1)) ;;
                *) bad=$((bad + 1)) ;;
            esac
        done < "$index"
        note=
        [ "$lane" != neutral ] || note=", $scoped out of scope, $unbuilt with no conversion built"
        echo "$name: $total files ($((total - held)) standalone, $held in containers), $bad differ$note"
        if [ "$lane" = neutral ]; then
            for rc in 3 4; do
                [ -s "$work/scope$rc.txt" ] || continue
                label="out of scope"
                [ "$rc" -eq 3 ] || label="not built"
                sort "$work/scope$rc.txt" | uniq -c | sort -rn | sed "s/^/  $label: /"
                : > "$work/scope$rc.txt"
            done
        fi
        [ "$bad" -eq 0 ] || failed=1
    done <<EOF
$formats
EOF
done

exit $failed
