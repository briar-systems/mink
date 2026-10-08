# cut the link-edit blobs of a Mach-O file into files, one per blob and slice
#
# usage: python3 -I cut.py <directory> <tag> <file>
#
# writes <directory>/<tag>.<slice>.<kind> for each of rebase, bind, weak, lazy,
# export, starts, dic, chained, sig, unwind_info and compact_unwind the file
# has, and <tag>.<slice>.seg<n> for every segment of a file with chained
# fixups. <slice> is thin, or the cputype of a slice of a fat file. an
# existing file of those names is overwritten, so each run gets a fresh
# directory.
import struct,sys,os
out=sys.argv[1]
tag=sys.argv[2]
path=sys.argv[3]
d=open(path,'rb').read()
def thin(off,name):
    magic=struct.unpack_from('<I',d,off)[0]
    if magic not in (0xfeedfacf,0xfeedface): print('skip',name); return
    is64=magic==0xfeedfacf
    cpu,sub,ft,ncmds,sz,fl=struct.unpack_from('<6I',d,off+4)
    p=off+(32 if is64 else 28)
    kinds={}; segs=[]
    for _ in range(ncmds):
        cmd,cs=struct.unpack_from('<II',d,p)
        if cmd in (0x22,0x80000022):
            ro,rs,bo,bs,wo,ws,lo,ls,eo,es=struct.unpack_from('<10I',d,p+8)
            for k,(o,s) in dict(rebase=(ro,rs),bind=(bo,bs),weak=(wo,ws),lazy=(lo,ls),export=(eo,es)).items(): kinds[k]=(o,s)
        elif cmd==0x80000033: kinds['export']=struct.unpack_from('<2I',d,p+8)
        elif cmd==0x26: kinds['starts']=struct.unpack_from('<2I',d,p+8)
        elif cmd==0x29: kinds['dic']=struct.unpack_from('<2I',d,p+8)
        elif cmd==0x80000034: kinds['chained']=struct.unpack_from('<2I',d,p+8)
        elif cmd==0x1d: kinds['sig']=struct.unpack_from('<2I',d,p+8)
        if cmd==0x19:
            nm=d[p+8:p+24].rstrip(b'\0').decode(); vmaddr,vmsize,fo,fs=struct.unpack_from('<4Q',d,p+24)
            segs.append((nm,fo,fs))
            nsects=struct.unpack_from('<I',d,p+64)[0]
            for k in range(nsects):
                so=p+72+80*k
                sn=d[so:so+16].rstrip(b'\0').decode(); addr,size=struct.unpack_from('<QQ',d,so+32); offs=struct.unpack_from('<I',d,so+48)[0]
                if sn in ('__unwind_info','__compact_unwind') and size:
                    open(f'{out}/{tag}.{name}.{sn[2:]}','wb').write(d[off+offs:off+offs+size]); print(tag,name,sn,size)
        p+=cs
    if 'chained' in kinds:
        for i,(nm,fo,fs) in enumerate(segs):
            open(f'{out}/{tag}.{name}.seg{i}','wb').write(d[off+fo:off+fo+fs])
    for k,(o,s) in kinds.items():
        if s==0: continue
        open(f'{out}/{tag}.{name}.{k}','wb').write(d[off+o:off+o+s])
        print(tag,name,k,s,'cpu',hex(cpu))
if struct.unpack_from('>I',d,0)[0]==0xcafebabe:
    n=struct.unpack_from('>I',d,4)[0]
    for i in range(n):
        cpu,sub,o,sz,al=struct.unpack_from('>5I',d,8+20*i); thin(o,hex(cpu))
else: thin(0,'thin')
