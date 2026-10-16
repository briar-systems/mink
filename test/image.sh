#!/usr/bin/env bash
# the lane of linked PE and Mach-O images, run on native runners by the windows
# and darwin lanes of ci.yml.
#
# usage: bash test/image.sh link <lane> <dir>
#        bash test/image.sh run <host> <dir>
#
# link runs on a linux host. for every host of test/image/hosts.tsv in <lane>
# ("all" for every host) it builds each case test/image/cases.tsv names for that
# host into <dir>/<host>, which must not exist: the case's sources compiled by
# clang for the host's triple, and mink link linking them into the image. the
# program must be built (mach build . -a cli) and clang on the path. <dir>/<host>
# also gets the case list and each case's expected output, so run reads nothing
# else of a case.
#
# run runs on the host itself, over a <dir> link made. it runs the host's check
# on each image, then the image, and compares its exit status and output with
# the case's.
#
# a host with no cases says so and passes. the exit status is the number of
# cases that failed
set -u

here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
repo=$(CDPATH= cd -- "$here/.." && pwd)

usage() { sed -n '2,/^[^#]/{/^#/p}' "$0" | sed 's/^# \{0,1\}//' >&2; exit 2; }
[ $# -eq 3 ] || usage

fails=0
fail() { echo "FAIL $1: $2"; fails=$((fails + 1)); }

# the rows of a table, comments and blank lines left out
rows() { grep -v -e '^#' -e '^[[:space:]]*$' "$1"; }

# "-" stands for an empty field, since read folds adjacent tabs
field() { [ "$1" = - ] || printf '%s' "$1"; }

# the row of test/image/hosts.tsv that names the host `$1`
host_row() { rows "$here/image/hosts.tsv" | awk -F '\t' -v h="$1" '$1 == h'; }

link_host() {
    local host=$1 triple=$2 suffix=$3 hostlink=$4 dir=$5
    local case at exit cflags link src base objs n=0
    mkdir -p "$dir" || exit 2
    : >"$dir/cases.tsv"
    while IFS=$'\t' read -r case at exit cflags link; do
        [ "$at" = "$host" ] || continue
        n=$((n + 1))
        objs=()
        for src in "$here/image/$case"/*; do
            base=$(basename -- "$src")
            case "$base" in
                *.c | *.s | *.S)
                    clang --target="$triple" $(field "$cflags") -c "$src" -o "$dir/$case-$base.o" 2>>"$dir/$case.cc" || { fail "$host $case" "$base does not compile, see $dir/$case.cc"; continue 2; }
                    objs+=("$dir/$case-$base.o") ;;
                *.o | *.obj) objs+=("$src") ;;
            esac
        done
        [ ${#objs[@]} -gt 0 ] || { fail "$host $case" "test/image/$case holds no inputs"; continue; }
        if ! "$mink" link "${objs[@]}" -o "$dir/$case$(field "$suffix")" $hostlink $(field "$link") 2>"$dir/$case.link"; then
            fail "$host $case" "the link is refused: $(cat "$dir/$case.link")"
            continue
        fi
        if [ -e "$here/image/$case/stdout" ]; then cp "$here/image/$case/stdout" "$dir/$case.want"; else : >"$dir/$case.want"; fi
        printf '%s\t%s\n' "$case" "$exit" >>"$dir/cases.tsv"
        echo "ok   $host $case linked"
    done < <(rows "$here/image/cases.tsv")
    [ $n -gt 0 ] || echo "$host: no cases"
}

run_host() {
    local host=$1 suffix=$2 check=$3 dir=$4
    local case exit img status n=0
    [ -f "$dir/cases.tsv" ] || { echo "image.sh: $dir/cases.tsv is missing, link the lane first" >&2; exit 2; }
    while IFS=$'\t' read -r case exit; do
        n=$((n + 1))
        img=$dir/$case$(field "$suffix")
        chmod +x "$img"
        if [ "$check" != - ] && ! $check "$img" >"$dir/$case.check" 2>&1; then
            fail "$host $case" "$check refuses the image: $(cat "$dir/$case.check")"
            continue
        fi
        "$img" >"$dir/$case.stdout" </dev/null
        status=$?
        [ "$status" = "$exit" ] || { fail "$host $case" "exits $status, not $exit"; continue; }
        cmp -s "$dir/$case.stdout" "$dir/$case.want" || { fail "$host $case" "prints '$(cat "$dir/$case.stdout")', not '$(cat "$dir/$case.want")'"; continue; }
        echo "ok   $host $case"
    done <"$dir/cases.tsv"
    [ $n -gt 0 ] || echo "$host: no cases"
}

verb=$1
dir=$3
case "$verb" in
    link)
        case "$(uname -s)/$(uname -m)" in
            Linux/x86_64)  host_dir=linux-x86_64 ;;
            Linux/aarch64) host_dir=linux-aarch64 ;;
            *) echo "image.sh: link runs on a linux host" >&2; exit 2 ;;
        esac
        mink=${MINK:-$repo/out/$host_dir/debug/bin/mink}
        [ -x "$mink" ] || { echo "image.sh: $mink is not built, run: mach build . -a cli" >&2; exit 2; }
        hosts=$(rows "$here/image/hosts.tsv" | awk -F '\t' -v l="$2" 'l == "all" || $2 == l')
        [ -n "$hosts" ] || { echo "image.sh: no host is in the lane $2" >&2; exit 2; }
        while IFS=$'\t' read -r host lane triple suffix hostlink check; do
            [ -e "$dir/$host" ] && { echo "image.sh: $dir/$host exists, name a fresh directory" >&2; exit 2; }
            link_host "$host" "$triple" "$suffix" "$hostlink" "$dir/$host"
        done <<<"$hosts"
        ;;
    run)
        row=$(host_row "$2")
        [ -n "$row" ] || { echo "image.sh: test/image/hosts.tsv has no host $2" >&2; exit 2; }
        IFS=$'\t' read -r host lane triple suffix hostlink check <<<"$row"
        run_host "$host" "$suffix" "$check" "$dir/$host"
        ;;
    *) usage ;;
esac
echo "$fails failed"
exit $fails
