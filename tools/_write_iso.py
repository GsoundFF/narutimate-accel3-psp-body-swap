import os
def rebuild_iso(cpk_path, iso_in, iso_out, cpk_iso_offset=123207680):
    """Replace the data.cpk region inside game.iso with patched cpk (same size)."""
    cpk=open(cpk_path,'rb').read()
    iso=bytearray(open(iso_in,'rb').read())
    if cpk_iso_offset+len(cpk)>len(iso):
        raise ValueError('cpk exceeds iso bounds')
    iso[cpk_iso_offset:cpk_iso_offset+len(cpk)]=cpk
    open(iso_out,'wb').write(bytes(iso))
    print('rebuilt iso ->',iso_out,'len',len(iso))

if __name__=='__main__':
    print('module ok')