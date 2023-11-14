#!/usr/bin/env python3
'''
Executable program for running injectIO for all AFL queue sessions by starting/stopping
RESim for each session.  This permits multi-packet replays which would otherwise corrupt
the origin bookmark if run repeatedly in a single Simics session.
'''
import os
import sys
import glob
import subprocess
import shutil
import threading
import signal
try:
    import ConfigParser
except:
    import configparser as ConfigParser
import threading
import time
import argparse
import json
import select
import shlex
import aflPath
import resimUtils
'''
'''
global stop_threads
def handler(signum, frame):
    global stop_threads
    print('sig handler with %d' % signum)
    stop_threads = True

def oneTrack(afl_list, resim_path, resim_ini, only_thread, no_page_faults, stop_threads, lgr, instance_path):
    if instance_path is not None:
        os.chdir(instance_path)
    here = os.getcwd()
    workspace = os.path.basename(here)
    lgr.debug('oneTrack, workspace: %s' % workspace)
    log = '/tmp/resim-%s.log' % workspace
    if only_thread:
        os.environ['ONE_DONE_PARAM2']='True'
    count = 0
    if no_page_faults:
        os.environ['ONE_DONE_PARAM3']='True'
    with open(log, 'wb') as fh:
        for f in afl_list:
            #os.chdir(here)
            lgr.debug('oneTrack, f: %s' % f)
            now_here = os.getcwd()
            #lgr.debug('oneTrack, here: %s, cwd says %s' % (here, now_here))
            os.environ['ONE_DONE_PATH'] = f
            base = os.path.basename(f)
            pdir = os.path.dirname(f)
            tdir = os.path.dirname(pdir)
            if os.path.basename(pdir) == 'manual_queue':
                trackdir = os.path.join(tdir, 'manual_trackio')
            else:
                trackdir = os.path.join(tdir, 'trackio')
            try:
                os.mkdir(trackdir)
            except:
                pass
            trackoutput = os.path.join(trackdir, base)
            if os.path.isfile(trackoutput):
                lgr.debug('%s path exists, skip it %s' % (workspace, trackoutput))
                continue
            try:
                os.open(trackoutput, os.O_CREAT | os.O_EXCL)
            except:
                continue
            lgr.debug('path for %s is %s' % (workspace, f))
    
            os.environ['ONE_DONE_PARAM'] = trackoutput
            #result = os.system('%s %s -n' % (resim_path, resim_ini))
            cmd = '%s %s -n' % (resim_path, resim_ini)
            now_here = os.getcwd()
            count = count + 1
            print("%s: starting monitor from %s count %d" % (workspace, now_here, count))
            lgr.debug("%s: starting monitor from %s count %d" % (workspace, now_here, count))
            resim_ps = subprocess.Popen(shlex.split(cmd), stdin=subprocess.PIPE, stdout=fh,stderr=fh)
            resim_ps.wait()
            if stop_threads():
                print('oneTrack sees stop, exiting.')
                lgr.debug('oneTrack %s sees stop, exiting.' % workspace)
                return
        
        print('done with %s' % workspace)

def main():
    global stop_threads
    here = os.getcwd()
    workspace = os.path.basename(here)
    log_name = 'runTrack-%s' % workspace
    lgr = resimUtils.getLogger(log_name, '/tmp/', level=None)
    script_path= os.path.dirname(os.path.realpath(__file__))
    parser = argparse.ArgumentParser(prog='runTrack', description='Run injectIO on all sessions in a target found by AFL.')
    parser.add_argument('ini', action='store', help='The RESim ini file used during the AFL session.')
    parser.add_argument('target', action='store', help='The afl output directory relative to AFL_OUTPUT in the ini file, or AFL_DATA in bashrc.')
    parser.add_argument('-o', '--only_thread', action='store_true', help='Only track references of single thread.')
    parser.add_argument('-n', '--no_page_faults', action='store_true', help='Do not watch page faults.  Only use when needed, will miss SEGV.')
    
    args = parser.parse_args()
    resim_ini = args.ini
    target = args.target
    
    ''' If multiple packets are within any of the crashing inputs,
        use a driver and trackIO.
    '''
    trackFD = None
    afl_list = [] 
    if os.path.isfile(target):
        ''' single file to report on '''
        afl_list = [target]
    else:
        #afl_list = aflPath.getTargetQueue(target, ws_filter=workspace)
        afl_list = aflPath.getTargetQueue(target)

    ''' remove any empty or corrupt track jsons '''
    track_list = aflPath.getAFLTrackList(target, ws_filter=workspace)
    for track_file in track_list:
        if os.path.isfile(track_file):
            with open(track_file) as fh:
                try:
                    jfile = json.load(fh)
                except:
                    print('removing empty or corrupt file %s' % track_file)
                    os.remove(track_file) 

    ''' The script to be called by RESim once it is initialized '''
    os.environ['ONE_DONE_SCRIPT'] = os.path.join(script_path, 'onedoneTrack.py')
    resim_path = os.path.join(os.getenv('RESIM_DIR'), 'simics', 'bin', 'resim')
    thread_list = []
    stop_threads=False
    signal.signal(signal.SIGINT, handler)
    signal.signal(signal.SIGTERM, handler)
    track_thread = threading.Thread(target=oneTrack, args=(afl_list, resim_path, resim_ini, args.only_thread, args.no_page_faults, lambda: stop_threads, lgr, None))
    thread_list.append(track_thread)
    track_thread.start()
   
    lgr.debug('Wait for threads to finish')
    for thread in thread_list:
        thread.join()     

if __name__ == '__main__':
    sys.exit(main())


