import os
import sys
import time
import logging
import subprocess
import elfText
import json
import re
import fnmatch
import winProg
import ntpath
try:
    import importlib
except:
    ''' must be py 2.7 '''
    import imp 
    pass
try:
    import ConfigParser
except:
    import configparser as ConfigParser

def getLogger(name, logdir, level=None):
    os.umask(000)
    try:
        os.makedirs(logdir)
    except:
        pass

    log_level = logging.DEBUG
    log_level_env = os.getenv('RESIM_LOG_LEVEL')
    if log_level_env is not None and log_level_env.lower() == 'info':
        log_level = logging.INFO
        
    lgr = logging.getLogger(name)
    #lhStdout = lgr.handlers[0]
    lgr.setLevel(log_level)
    fh = logging.FileHandler(logdir+'/%s.log' % name)
    fh.setLevel(log_level)
    frmt = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    fh.setFormatter(frmt)
    lgr.addHandler(fh)
    #lgr.removeHandler(lhStdout)
    lgr.info('Start of log from %s.py' % name)
    ch = logging.StreamHandler()
    ch.setLevel(logging.ERROR)
    ch.setFormatter(frmt)
    lgr.addHandler(ch)
    #lgr.propogate = False
    return lgr

def isParallel():
    ''' Determine if the current workspace is a parallel clone '''
    here = os.getcwd()
    ws = os.path.basename(here)
    if ws.startswith('resim_') and os.path.exists('resim_ctl.fifo'):
        return True
    else:
        return False

def getIdaDataFromIni(prog, ini):
    retval = None
    resim_ida_data = os.getenv('RESIM_IDA_DATA')
    if resim_ida_data is None:
        print('ERROR: RESIM_IDA_DATA not defined')
    else:
        root_fs = getIniTargetValue(ini, 'RESIM_ROOT_PREFIX')
        base = os.path.basename(root_fs)
        #retval = os.path.join(resim_ida_data, base, prog, prog)
        retval = os.path.join(resim_ida_data, base, prog)
    return retval

def getOldIdaDataFromIni(prog, ini):
    retval = None
    resim_ida_data = os.getenv('RESIM_IDA_DATA')
    if resim_ida_data is None:
        print('ERROR: RESIM_IDA_DATA not defined')
    else:
        root_fs = getIniTargetValue(ini, 'RESIM_ROOT_PREFIX')
        base = os.path.basename(root_fs)
        retval = os.path.join(resim_ida_data, base, prog, prog)
    return retval

def getIdaData(full_path, root_prefix, lgr=None):
    ''' get the ida data path, providing backward compatability with old style paths '''
    retval = None
    resim_ida_data = os.getenv('RESIM_IDA_DATA')
    if resim_ida_data is None:
        print('ERROR: RESIM_IDA_DATA not defined')
        if lgr is not None:
            lgr.error('RESIM_IDA_DATA not defined')
            return None
    resim_image = os.getenv('RESIM_IMAGE')
    if resim_image is None:
        print('ERROR: RESIM_IMAGE not defined')
        return None
    ida_analysis = os.getenv('IDA_ANALYSIS')
    if ida_analysis is None:
        print('ERROR: IDA_ANALYSIS not defined')
        return None
    if full_path.startswith(resim_image):
        offset = len(resim_image)+1
        remain = full_path[offset:]
        retval = os.path.join(resim_ida_data, remain)
        if lgr is not None:
            lgr.debug('getIdaData is image path full_path %s, remain %s return %s' % (full_path, remain, retval))
    elif full_path.startswith(ida_analysis):
        offset = len(ida_analysis)+1
        remain = full_path[offset:]
        retval = os.path.join(resim_ida_data, remain)
        if lgr is not None:
            lgr.debug('getIdaData is analysis path full_path %s, remain %s return %s' % (full_path, remain, retval))

    else: 
        if lgr is not None:
            lgr.debug('full_path %s' % full_path)
        base = os.path.basename(full_path)
        root_base = os.path.basename(root_prefix)
        if lgr is not None:
            lgr.debug('root_prefix %s' % root_prefix)
        new_path = os.path.join(resim_ida_data, root_base, base)
        old_path = os.path.join(resim_ida_data, base)
        if lgr is not None:
            lgr.debug('old %s' % old_path)
        if lgr is not None:
            lgr.debug('new %s' % new_path)
        if not os.path.isdir(new_path): 
            if os.path.isdir(old_path):
                ''' Use old path style '''
                retval = os.path.join(old_path, base)
                if lgr is not None:
                    lgr.debug('Using old style ida data path %s' % retval)
            else:
                retval = os.path.join(new_path, base)
                if lgr is not None:
                    lgr.debug('Using new style ida data path %s' % retval)
        else:
            retval = os.path.join(new_path, base)
            if lgr is not None:
                lgr.debug('no existing ida data path %s' % retval)
        
    return retval

def doLoad(module, path):
    #print('version is %d %d' % (sys.version_info[0], sys.version_info[1]))
    if sys.version_info[0] == 3:
        spec = importlib.util.spec_from_file_location(module, path)
        retval = importlib.util.module_from_spec(spec)
        sys.modules[module] = retval
        spec.loader.exec_module(retval)
    else: 
        retval = imp.load_source(module, path)
    return retval

def getPacketFilter(packet_filter, lgr):
    retval = None
    if packet_filter is not None:
        file_path = './%s.py' % packet_filter
        abs_path = os.path.abspath(file_path)
        if os.path.isfile(abs_path):
            retval = doLoad(packet_filter, abs_path)
            lgr.debug('afl using AFL_PACKET_FILTER %s' % packet_filter)
        else:
            file_path = './%s' % packet_filter
            abs_path = os.path.abspath(file_path)
            if os.path.isfile(abs_path):
                retval = doLoad(packet_filter, abs_path)
                lgr.debug('afl using AFL_PACKET_FILTER %s' % packet_filter)
            else:
                lgr.error('failed to find filter at %s' % packet_filter)
                raise Exception('failed to find filter at %s' % packet_filter)
    return retval

def getBasicBlocks(prog, ini=None, lgr=None, root_prefix=None, os_type=None):
    blocks = None
    analysis_path = getAnalysisPath(ini, prog, root_prefix=root_prefix, lgr=lgr)
    #print('analysis_path at %s' % analysis_path)
    if lgr is not None:
        lgr.debug('getBasicBlocks analysis_path %s' % analysis_path)
    prog_elf = None
    if os_type is None:
        os_type = getIniTargetValue(ini, 'OS_TYPE')
    if analysis_path is not None:
        prog_path = getProgPathFromAnalysis(analysis_path, ini, lgr=lgr, root_prefix=root_prefix) 
        if lgr is not None:
            lgr.debug('getBasicBlocks got prog_path %s' % prog_path)
        #print('getBasicBlocks got prog_path %s' % prog_path)
        if os_type.startswith('WIN'):
            if lgr is not None:
                lgr.debug('is windows')
            prog_elf = winProg.getText(prog_path, lgr)
        else:
            prog_elf = elfText.getText(prog_path, lgr)
        #print('prog addr 0x%x size %d' % (prog_elf.text_address, prog_elf.text_size))
        if lgr is not None:
            if prog_elf.text_start is not None:
                lgr.debug('prog text_start 0x%x text_size %d' % (prog_elf.text_start, prog_elf.text_size))
            else:
                lgr.debug('prog text_start is None for %s' % prog_path)
        block_file = analysis_path+'.blocks'
        #print('block file is %s' % block_file)
        if not os.path.isfile(block_file):
            if lgr is not None:
                   lgr.debug('block file not found %s, see if it is a link?' % block_file)
            if os.path.islink(prog_file):
                real = os.readlink(prog_file)
                parent = os.path.dirname(prog_file)
                block_file = os.path.join(parent, (real+'.blocks'))
                if not os.path.isfile(block_file):
                    if lgr is not None:
                       lgr.debug('block file not found %s' % block_file)
                    print('block file not found %s' % block_file)
                    return
            else:
               print('block file (or link) not found %s' % block_file)
               return
        with open(block_file) as fh:
            blocks = json.load(fh)
    return blocks, prog_elf

def getOneBasicBlock(prog, addr, os_type, root_prefix, lgr=None):
    #print('getOneBasicBloc os %s root_prefix %s' % (os_type, root_prefix))
    blocks, dumb = getBasicBlocks(prog, root_prefix=root_prefix, os_type=os_type, lgr=lgr)
    retval = None
    if blocks is not None:
        for fun in blocks:
            for bb in blocks[fun]['blocks']:
                #print('compare 0x%x to 0x%x' % (addr, bb['start_ea']))
                if bb['start_ea'] == addr:
                    retval = bb
                    break
            if retval is not None:
                break    
    else:
        print('ERROR: getOneBasicBlock, blocks was none')
    return retval

def findBB(blocks, addr):
    retval = None
    for fun in blocks:
        for bb in blocks[fun]['blocks']:
            if addr >= bb['start_ea'] and addr <= bb['end_ea']:
                retval =  bb['start_ea']
                break
    return retval

def findEndBB(blocks, addr):
    retval = None
    for fun in blocks:
        for bb in blocks[fun]['blocks']:
            #print('compare 0x%x (%s) to 0x%x (%s)' % (bb['start_ea'], type(bb['start_ea']), addr, type(addr)))
            if addr == bb['start_ea']:
                retval =  bb['end_ea']
                break
        if retval is not None:
            break
    if retval is None:
        print('failed to find 0x%x in basic blocks' % addr)
        exit(1)
    return retval
 
def isPrintable(thebytes, ignore_zero=False):
    gotone=False
    retval = True
    zcount = 0
    for b in thebytes:
        if ignore_zero and b == 0 and zcount == 0:
            zcount = zcount + 1 
        elif b is None or b > 0x7f or (b < 0x20 and b != 0xa and b != 0xd):
            retval = False
            break
        elif b > 0x20:
            gotone=True
            zcount = 0
    if not gotone:
        retval = False 
    return retval

def getHexDump(b):
    if len(b) == 0:
        return ""
    count = 0
    for i in reversed(b):
        if i is None or i > 0:
            break
        count = count + 1
    end = len(b) - count
    b = b[:end]
    s2 = "".join([chr(i) if i is not None and 32 <= i <= 127 else "." for i in b])
    if not isPrintable(b):
        s1 = ''
        for i in b:
            if i is None:
                break
            val = '%02x' % i
            s1 = s1+ val
        #s1 = "".join([f"{i:02x}" for i in b])
        #s1 = s1[0:23] + " " + s1[23:]
        width = 48
        #return (f"{s1:<{width}}  |{s2}|") # parameterized width
        return '%s |%s|' % (s1, s2)
    else:
        return s2


def getIniTargetValue(input_ini_file, field, target=None, lgr=None):
    retval = None
    config = ConfigParser.ConfigParser()
    config.optionxform = str
    if not input_ini_file.endswith('.ini'):
        ini_file = '%s.ini' % input_ini_file
    else:
        ini_file = input_ini_file
    if not os.path.isfile(ini_file):
        print('File not found: %s' % ini_file)
        exit(1)
    config.read(ini_file)
    if target is None:
        for name, value in config.items('ENV'):
            if name == 'RESIM_TARGET':
                target = value
                break
    if lgr is not None:
        lgr.debug('getInitTargetValue target %s' % target)
    got_target = False
    if target is not None:
        for section in config.sections():
            if section == target:
                got_target = True
                for name, value in config.items(section):
                    if name == field:
                        retval = value 
                        break
    if not got_target:
        print('ERROR filed to find target %s in ini file %s' % (target, ini_file))
        if lgr is not None:
            lgr.error('filed to find target %s in ini file %s' % (target, ini_file))
       
    if retval is not None and retval.startswith('$'):
        env, path = retval.split('/',1)
        env_value = os.getenv(env[1:]) 
        retval = os.path.join(env_value, path)
    return retval

def findPattern(path: str, glob_pat: str, ignore_case: bool = False):
    ''' only works if pattern is glob-like, does not recurse '''
    rule = re.compile(fnmatch.translate(glob_pat), re.IGNORECASE) if ignore_case \
            else re.compile(fnmatch.translate(glob_pat))
    return [n for n in os.listdir(path) if rule.match(n)]

def findFrom(name, from_dir):
    for root, dirs, files in os.walk(from_dir):
        if name in files:
            retval = os.path.join(from_dir, root, name)
            abspath = os.path.abspath(retval)
            return abspath
    return None

def findListFrom(pattern, from_dir):
    retval = []
    for root, dirs, files in os.walk(from_dir):
        flist = fnmatch.filter(files, pattern)
        for f in flist:
            retval.append(f)
    return retval

def getfileInsensitive(path, root_prefix, root_subdirs, lgr, force_look=False):
    lgr.debug('getfileInsensitve path %s' % path)
    got_it = False
    retval = root_prefix
    cur_dir = root_prefix
    if '/' in path:
        parts = path.split('/')
        for p in parts[:-1]:
            #lgr.debug('getfileInsensitve part %s cur_dir %s' % (p, cur_dir))
            dlist = [ name for name in os.listdir(cur_dir) if os.path.isdir(os.path.join(cur_dir, name)) ]

            for d in dlist:
                if d.upper() == p.upper():
                    retval = os.path.join(retval, d)
                    cur_dir = os.path.join(cur_dir, d)
                    break
        p = parts[-1]
        #lgr.debug('getfileInsensitve cur_dir %s last part %s' % (cur_dir, p))
        flist = os.listdir(cur_dir)
        for f in flist:
            if f.upper() == p.upper():
                retval = os.path.join(retval, f) 
                got_it = True
                break
    else:
        if not force_look and len(root_subdirs) == 0:
            if lgr is not None:
                 lgr.warning('getfileInsensitive RELATIVE %s root: %s   NOT LOOKING, return none' % (path, root_prefix))
        else:
            lgr.debug('getfileInsensitive')
            if len(root_subdirs) > 0:
                for subpath in root_subdirs:
                    top_path = os.path.join(root_prefix, subpath)
                    #lgr.debug('getfileInsensitive walk from %s' % top_path)
                    for root, dirs, files in os.walk(top_path):
                        for f in files:
                            if f.upper() == path.upper():
                                retval = os.path.join(top_path, root, f)
                                abspath = os.path.abspath(retval)
                                return abspath
            else:
                top_path = os.path.join(root_prefix)
                #lgr.debug('getfileInsensitive walk from %s' % top_path)
                for root, dirs, files in os.walk(top_path):
                    for f in files:
                        if f.upper() == path.upper():
                            retval = os.path.join(top_path, root, f)
                            abspath = os.path.abspath(retval)
                            return abspath
        return None


    if not got_it:
        retval = None
    return retval

def realPath(full_path):
        retval = full_path
        if os.path.islink(full_path):
            parent = os.path.dirname(full_path)
            actual = os.readlink(full_path)
            retval = os.path.join(parent, actual)
        return retval

def getProgPathFromAnalysis(full_analysis_path, ini, lgr=None, root_prefix=None):
    analysis_path = os.getenv('IDA_ANALYSIS')
    if analysis_path is None:
        if lgr is not None:
            lgr.error('getProgPathFromAnalysis no IDA_ANALYSIS defined as env variable.')
        else:
            print('ERROR getProgPathFromAnalysis no IDA_ANALYSIS defined as env variable.')
        return None
    relative = full_analysis_path[len(analysis_path)+1:] 
    if lgr is not None:
        lgr.debug('getProgPathFromAnalysis relative is %s' % relative)
    if root_prefix is None:
        root_prefix = getIniTargetValue(ini, 'RESIM_ROOT_PREFIX', lgr=lgr)
    if lgr is not None:
        lgr.debug('getProgPathFromAnalysis root_prefix %s' % root_prefix)
    retval = os.path.join(os.path.dirname(root_prefix), relative)
    return retval

def soMatch(fname, cache, lgr):
    # look for matches to handle things like libfu.so.0 as the fname vs a cache with something like libfu.so.0.0.1.funs
    retval = None
    base = os.path.basename(fname).upper()
    for item in cache:
        upper_item = item.upper()
        if upper_item.startswith(base) and upper_item.endswith('.FUNS'):
            if lgr  is not None:
                #lgr.debug('resimUtils soMatch found match %s' % item)
                retval = item
    return retval
   
def getWinPath(path, root_prefix, lgr=None): 
    if path.startswith('/??/C:/') or path.startswith('/??/c:/'):
        if os.path.isdir(os.path.join(root_prefix, 'C:')) or os.path.isdir(os.path.join(root_prefix, 'c:')):
            path = path[4:]
        else:
            path = path[7:]
    elif path.startswith('/??/D:/') or path.startswith('/??/d:/'):
        if lgr is not None:
            lgr.debug('resimUtils getWinPath is D:')
        if os.path.isdir(os.path.join(root_prefix, 'D:')) or os.path.isdir(os.path.join(root_prefix, 'd:')):
            path = path[4:]
            if lgr is not None:
                lgr.debug('resimUtils getWinPath is D: is dir path now %s' % path)
        else:
            if lgr is not None:
                lgr.debug('resimUtils getWinPath is D: but not a subdir off root')
            path = path[7:]
    elif path.startswith('/'):
        path = path[1:]
    return path

def getAnalysisPath(ini, fname, fun_list_cache = [], lgr=None, root_prefix=None):
    retval = None
    if lgr is not None:
        lgr.debug('resimUtils getAnalyisPath find %s' % fname)
    analysis_path = os.getenv('IDA_ANALYSIS')
    if analysis_path is None:
        lgr.error('resimUtils getAnalysis path IDA_ANALYSIS not defined')
    quick_check = fname+'.funs'
    if fname.startswith(analysis_path) and os.path.isfile(quick_check):
        #if lgr is not None:
        #    lgr.debug('resimUtils getAnalyisPath quick check got %s' % fname)
        retval = fname
    else:
        #lgr.debug('resimUtils getAnalysisPath fname %s' % fname)
        if root_prefix is None: 
            root_prefix = getIniTargetValue(ini, 'RESIM_ROOT_PREFIX')
        root_dir = os.path.basename(root_prefix)
        top_dir = os.path.join(analysis_path, root_dir)
        if fname.startswith('/'):
            analysis_path = os.path.join(top_dir, fname[1:])+'.funs'
            #lgr.debug('try %s' % analysis_path)
            if os.path.isfile(analysis_path):
                retval = analysis_path[:-5]
       
    if retval is None:    
        #if lgr is not None:
        #    lgr.debug('resimUtils getAnalysisPath root_dir %s top_dir %s' % (root_dir, top_dir))
        if len(fun_list_cache) == 0:
            fun_list_cache = findListFrom('*.funs', top_dir)
            #if lgr is not None:
            #    lgr.debug('resimUtils getAnalysisPath loaded %d fun files into cache top_dir %s' % (len(fun_list_cache), top_dir))

        fname = fname.replace('\\', '/')
        if root_prefix is None:
            if fname.startswith('/??/C:/'):
                fname = fname[7:]
        else:
            fname = getWinPath(fname, root_prefix, lgr=lgr)

        base = os.path.basename(fname)+'.funs'
        #if base.upper() in map(str.upper, fun_list_cache):
        is_match = soMatch(fname, fun_list_cache, lgr)
        if is_match is not None:
            parent = os.path.dirname(fname)
            with_funs = os.path.join(parent, is_match)
            #with_funs = fname+'.funs'
            #if lgr is not None:
            #    lgr.debug('resimUtils getAnalsysisPath look for path for %s top_dir %s' % (with_funs, top_dir))
            retval = getfileInsensitive(with_funs, top_dir, [], lgr, force_look=True)
            if retval is not None:
                #lgr.debug('resimUtils getAnalsysisPath got %s from %s' % (retval, with_funs))
                retval = retval[:-5]
        else:
            if lgr is not None:
                lgr.debug('resimUtils getAnalysisPath %s not in cache' % base)
            pass

    return retval

def isClib(in_lib_file):
    retval = False
    lib_file = os.path.basename(in_lib_file) 
    if lib_file is not None:
        lf = lib_file.lower()
        if 'libc' in lf or 'libstdc' in lf or 'kernelbase' in lf or 'ws2_32' in lf or 'msvcr.dll' in lf or 'msvcp.dll' in lf or 'kernel32' in lf or 'ucrtbase' in lf:
            retval = True
        elif lf.endswith('.dll'):
            if 'msvcr' in lf or 'msvcp' in lf or 'kernel32' in lf or 'ucrtbase' in lf:
                retval = True
        elif lf.startswith('ld-'):
            # loader as libc
            retval = True
    return retval

def getLoadOffsetFromSO(so_json, prog, lgr=None):
    retval = None
    wrong_file = False
    if prog is None:
        if lgr is not None: 
            lgr.debug('resimUtils getLoadOffsetFromSO prog is None, returning offset 0')
        return 0
    offset = 0
    if lgr is not None: 
        lgr.debug('resimUtils getLoadOffsetFromSO prog: %s  so_json[proc] %s' % (prog, so_json['prog']))
    so_prog = os.path.basename(so_json['prog'])
    if so_prog == prog:
       #print('0x%x is in prog' % bb['start_ea'])  
       prog_start = so_json['prog_start']
       if 'relocate' in so_json:
           offset = prog_start 
           if lgr is not None:
               lgr.debug('resimUtils getLoadOffsetFromSO is prog: %s and is relocate, set offset to prog_start 0x%x' % (prog, prog_start))
       pass
    else:
       wrong_file = True
       for section in so_json['sections']:
           #print('section file is %s' % section['file'])
           if lgr is not None:
               lgr.debug('section file is %s' % section['file'])
           if section['file'].endswith(prog):
               offset = section['locate']
               if lgr is not None:
                   lgr.debug('got section, offset is 0x%x' % offset)
               wrong_file = False
    if not wrong_file:
        retval = offset
    return retval 

def getFree():
    cmd = "free"
    with subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE) as ps:
        output = ps.communicate()
        use_available = False
        for line in output[0].decode("utf-8").splitlines():
             if 'available' in line:
                 use_available = True
             if line.startswith('Mem:'):
                 parts = line.split()
                 tot = int(parts[1])
                 if use_available:
                     free = int(parts[6])
                 else:
                     free = int(parts[3])
                 #print('tot %s   free %s' % (tot, free))             
                 percent = (free / tot) * 100
                 return int(percent)
    return None

