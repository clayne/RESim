'''
 * This software was created by United States Government employees
 * and may not be copyrighted.
 * Redistribution and use in source and binary forms, with or without
 * modification, are permitted provided that the following conditions
 * are met:
 * 1. Redistributions of source code must retain the above copyright
 *    notice, this list of conditions and the following disclaimer.
 * 2. Redistributions in binary form must reproduce the above copyright
 *    notice, this list of conditions and the following disclaimer in the
 *    documentation and/or other materials provided with the distribution.
 *
 * THIS SOFTWARE IS PROVIDED BY THE AUTHOR ``AS IS'' AND ANY EXPRESS OR
 * IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED
 * WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
 * DISCLAIMED.  IN NO EVENT SHALL THE AUTHOR BE LIABLE FOR ANY DIRECT,
 * INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES
 * (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR
 * SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION)
 * HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT,
 * STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN
 * ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
 * POSSIBILITY OF SUCH DAMAGE.
'''
import time
import idaapi
import idaversion
import idc
import idautils
import bpUtils
import gdbProt
#import okTextForm
import waitDialog
import functionSig
#import reHooks
#import dbgHooks
import regFu
import menuMod
import bookmarkView
import idaSIM
import stackTrace
import dataWatch
import branchNotTaken
import writeWatch
import reHooks
import dbgHooks
import ida_dbg
import menuMod
import idbHooks

'''
idaapi.require("idaSIM")
idaapi.require("stackTrace")
idaapi.require("dataWatch")
idaapi.require("branchNotTaken")
idaapi.require("writeWatch")
idaapi.require("bookmarkView")
idaapi.require("reHooks")
idaapi.require("dbgHooks")
idaapi.require("menuMod")
'''
from idaapi import Choose
'''
    IDA script to reverse execution of Simics to the next breakpoint.
    Since IDA does not know about reverse exectution, the general approach is to 
    tell Simics to reverse and then tell IDA to continue forward.
    The script installs its functions as a hotkeys. 
    See showHelp below
'''
#reg_list =['eax', 'ebx', 'ecx', 'edx', 'esi', 'edi', 'ebp', 'esp', 'ax', 'bx', 'cx', 'dx', 'ah', 'al', 'bh', 'bl', 'ch', 'cl', 'dh', 'dl']
#reg_list = idaapi.ph_get_regnames()

def showHelp(prompt=False):
    print('in showHelp')
    lines = {}
    lines['overview'] = """
CGC Monitor IDA Client Help
The IDA gdb client is enhanced to support reverse execution; use of
execution bookmarks; and functions such as reversing until a specified
register is modified.  The functions are available through the "Debug"
menu.   IDA has also been extended to include a "Bookmarks" tabbed window
that lists execution bookmarks, which can be appended via a right click.

The GCC Monitor will have broken execution at a PoV or signal, as reflected
in the last bookmark in the Bookmarks tabbed window.

    """
    lines['hotkeys'] = """
The script installs its functions as a hotkeys. Note use <fn> key on Mac 
 
    Alt-Shift-F9 reverse
    Alt-Shift-F8 reverse step over
    Alt-Shift-F7 reverse step into 
    Alt-Shift-F4 reverse to cursor
    Alt-F6       reverse until just before current function is called
    Alt-Shift-r  reverse to previous write to highlighted register
    Alt-Shift-a  reverse to previous write to highlighted (or entered) address
    Alt-Shift-s  reverse to previous write to current stack location
    Alt-Shift-o  jump to initial debug eip (just before fault) 
    Alt-Shift-t  jump to start of process
    Alt-Shift-p  set an execution bookmark
    Alt-Shift-j  jump to a bookmark (chosen from list)
    Alt-Shift-u  run forward until in user space (useful if found missing page)
    Alt-Shift-q  quit ida debug session
    Alt-Shift-h  show help
    """
    print(lines['hotkeys'])
    #print('do okTextForm')
    #f = okTextForm.okTextForm(lines, prompt)
    #return f.go()

def int32(x):
  if x>0xFFFFFFFF:
    raise OverflowError
  if x>0x7FFFFFFF:
    x=int(0x100000000-x)
    if x<2147483648:
      return -x
    else:
      return -2147483648
  return x

''' is test a subpart of the target register? '''
def isRegisterPart(target, test):
        if target == test:
            return True
        reg_letter = target[0]
        if target[0] == 'e':
            reg_letter = target[1]
        if test[0] == reg_letter:
            return True
        else:
            return False
    
                        
'''
    Read a return string generated by Simics and parse out the EIP
'''
def getAddress(simicsString):
    if simicsString is None or type(simicsString) is int:
        return None
    # simics 4.8 is spitting multiple lines when it hits a break or cycle
    line = None
    try:
        lines = simicsString.split('\n')
    except:
        print('getAddress failed splitting lines')
        return None
    # hack to get the last simics output with an eip in it
    for line in reversed(lines):
        #print 'check %s' % line
        if 'cs:' in line or 'ip:' in line:
            simicsString = line
            break
    #print('new string is %s' % simicsString)
    toks = None
    try:
        toks = simicsString.split(' ')
    except:
        print('getAddress not a string to split')
        return None
    addr = None
    for tok in toks:
        #print 'look at tok [%s]' % tok
        if tok.find("skip_this_address") != -1:
            print('SKIP THIS ADDRESS')
            return 0
        if tok.startswith('cs:') or tok.startswith('ip:'):
                #print 'got cs! %s' % tok
                try:
                    addr = int(tok[3:], 16)
                except:
                    print('exception in getAddress trying to get int from tok %s' % tok)
                    print('failed to get int 16 from %s' % tok[3:])
                break
    return addr

def getCPL():
        cs = idaversion.get_reg_value("CS")
        return cs & 3
def generateSignatures():
        functionSig.genSignatures()
    
def querySignatures():
        functionSig.querySignatures()
    
def getTagValue(line, find_tag):
        parts = line.split()
        for part in parts:
            if ':' in part:
                tag, value = part.split(':',1)
                if tag.strip() == find_tag:
                    return value
        return None




def doKeyMap(isim):
    menuMod.register(isim)
    menuMod.attach()
    '''
    idaapi.CompileLine('static key_alt_shift_d() { RunPythonStatement("isim.testDialog()"); }')
    AddHotkey("Alt+Shift+d", 'key_alt_shift_d')

    #idaapi.CompileLine('static key_f9() { RunPythonStatement("isim.continueForward()"); }')
    #AddHotkey("F9", 'f9')
    #idaapi.add_menu_item("Debugger/Attach to process", "continue", "F9", 0, isim.continueForward, None)

    idaapi.CompileLine('static key_alt_R() { RunPythonStatement("isim.rebase()"); }')
    AddHotkey("Alt+Shift+R", 'key_alt_R')
    idaapi.add_menu_item("Debugger/Attach to process", "Rebase", "Alt+Shift+R", 0, isim.rebase, None)

    idaapi.CompileLine('static key_alt_f9() { RunPythonStatement("isim.doReverse()"); }')
    AddHotkey("Alt+Shift+F9", 'key_alt_f9')
    idaapi.add_menu_item("Debugger/Attach to process", "^ Reverse continue process", "Alt+Shift+F9", 0, isim.doReverse, None)
    
    idaapi.CompileLine('static key_alt_f8() { RunPythonStatement("isim.doRevStepOver()"); }')
    AddHotkey("Alt+Shift+F8", 'key_alt_f8')
    idaapi.add_menu_item("Debugger/Run until return", "^ Rev step over", "Alt+Shift+F8", 0, isim.doRevStepOver, None)

    idaapi.CompileLine('static f8() { RunPythonStatement("isim.doStepOver()"); }')
    AddHotkey("F8", 'f8')
    #idaapi.add_menu_item("Debugger/Step over", "step over", "F8", 0, doStepOver, None)
    
    idaapi.CompileLine('static key_alt_f7() { RunPythonStatement("isim.doRevStepInto()"); }')
    AddHotkey("Alt+Shift+F7", 'key_alt_f7')
    idaapi.add_menu_item("Debugger/Step over", "^ Rev step into", "Alt-Shift-F7", 0, isim.doRevStepInto, None)
    
    idaapi.CompileLine('static f7() { RunPythonStatement("isim.doStepInto()"); }')
    AddHotkey("F7", 'f7')
    #idaapi.add_menu_item("Debugger/Step into", "step into", "F7", 0, doStepInto, None)

    #idaapi.CompileLine('static key_alt_shift_f7() { RunPythonStatement("doRevStepInto()"); }')
    #AddHotkey("Alt+Shift+F7", 'key_alt_shift_f7')
    
    #idaapi.CompileLine('static key_alt_f7() { RunPythonStatement("doRevFinish()"); }')
    #AddHotkey("Alt+F7", 'key_alt_f7')

    idaapi.CompileLine('static key_alt_f6() { RunPythonStatement("doRevFinish()"); }')
    AddHotkey("Alt+F6", 'key_alt_f6')
    idaapi.add_menu_item("Debugger/Run to cursor", "^ Rev until call", "Alt+F6", 0, isim.doRevFinish, None)
    
    idaapi.CompileLine('static key_alt_shift_f4() { RunPythonStatement("isim.doRevToCursor()"); }')
    AddHotkey("Alt+Shift+F4", 'key_alt_shift_f4')
    idaapi.add_menu_item("Debugger/Run to cursor", "^ Rev to cursor", "Alt+Shift+F4", 1, isim.doRevToCursor, None)
    
    idaapi.CompileLine('static key_alt_shift_s() { RunPythonStatement("isim.wroteToSP()"); }')
    AddHotkey("Alt+Shift+s", 'key_alt_shift_s')
    idaapi.add_menu_item("Debugger/^ Rev to cursor", "^ Wrote to [ESP]", "Alt+Shift+s", 1, isim.wroteToSP, None)
    
    idaapi.CompileLine('static key_alt_shift_a() { RunPythonStatement("isim.wroteToAddressPrompt()"); }')
    AddHotkey("Alt+Shift+a", 'key_alt_shift_a')
    idaapi.add_menu_item("Debugger/^ Rev to cursor", "^ Wrote to address...", "Alt+Shift+a", 1, isim.wroteToAddressPrompt, None)
    
    idaapi.CompileLine('static key_ctrl_shift_a() { RunPythonStatement("isim.trackAddressPrompt()"); }')
    AddHotkey("Ctrl+Shift+a", 'key_ctrl_shift_a')
    idaapi.add_menu_item("Debugger/^ Rev to cursor", "^ track address...", "Ctrl+Shift+a", 1, isim.trackAddressPrompt, None)
    
    idaapi.CompileLine('static key_alt_shift_r() { RunPythonStatement("isim.wroteToRegister()"); }')
    AddHotkey("Alt+Shift+r", 'key_alt_shift_r')
    idaapi.add_menu_item("Debugger/^ Rev to cursor", "^ Wrote to register...", "Alt+Shift+r", 1, isim.wroteToRegister, None)
    
    idaapi.CompileLine('static key_ctrl_shift_r() { RunPythonStatement("isim.trackToRegister()"); }')
    AddHotkey("Ctrl+Shift+r", 'key_ctrl_shift_r')
    idaapi.add_menu_item("Debugger/^ Rev to cursor", "^ track register...", "Ctrl+Shift+r", 1, isim.trackRegister, None)
    
    idaapi.CompileLine('static key_alt_shift_m() { RunPythonStatement("isim.showSimicsMessage()"); }')
    AddHotkey("Alt+Shift+m", 'key_alt_shift_m')
    
    idaapi.CompileLine('static key_alt_shift_o() { RunPythonStatement("isim.goToOrigin()"); }')
    AddHotkey("Alt+Shift+o", 'key_alt_shift_o')
    
    idaapi.CompileLine('static key_alt_shift_t() { RunPythonStatement("isim.goToBegin()"); }')
    AddHotkey("Alt+Shift+t", 'key_alt_shift_t')
    
    idaapi.CompileLine('static key_alt_shift_h() { RunPythonStatement("isim.showHelp()"); }')
    AddHotkey("Alt+Shift+h", 'key_alt_shift_h')
    idaapi.add_menu_item("Help/Ida home page", "CGC Ida client help", "Alt+Shift+h", 0, showHelp, None)
    
    idaapi.CompileLine('static key_alt_shift_p() { RunPythonStatement("isim.askSetBookmark()"); }')
    AddHotkey("Alt+Shift+p", 'key_alt_shift_p')
    
    idaapi.CompileLine('static key_alt_shift_j() { RunPythonStatement("isim.chooseBookmark()"); }')
    AddHotkey("Alt+Shift+j", 'key_alt_shift_j')
    
    idaapi.CompileLine('static key_alt_shift_l() { RunPythonStatement("isim.listBookmarks()"); }')
    AddHotkey("Alt+Shift+l", 'key_alt_shift_l')
    
    idaapi.CompileLine('static key_alt_shift_k() { RunPythonStatement("isim.highlightedBookmark()"); }')
    AddHotkey("Alt+Shift+k", 'key_alt_shift_k')
    
    idaapi.CompileLine('static key_alt_shift_u() { RunPythonStatement("isim.runToUserSpace()"); }')
    AddHotkey("Alt+Shift+u", 'key_alt_shift_u')
    idaapi.add_menu_item("Debugger/^ Rev to cursor", "Run to user space", "Alt+Shift+u", 1, isim.runToUserSpace, None)
    

    idaapi.CompileLine('static key_alt_c() { RunPythonStatement("isim.runToSyscall()"); }')
    AddHotkey("Alt+c", 'key_alt_c')
    idaapi.add_menu_item("Debugger/O Run to/", "Run to syscall", "Alt+c", 1, isim.runToSyscall, None)
    
    
    idaapi.CompileLine('static key_alt_shift_c() { RunPythonStatement("isim.revToSyscall()"); }')
    AddHotkey("Alt+Shift+c", 'key_alt_shift_c')
    idaapi.add_menu_item("Debugger/^ Rev to cursor", "Rev to syscall", "Alt+Shift+c", 1, isim.revToSyscall, None)
    
    idaapi.add_menu_item("Debugger/O Run to/", "Run to clone child", None, 1, isim.runToClone, None)
    idaapi.add_menu_item("Debugger/O Run to/", "Run to text segment", None, 1, isim.runToText, None)
    idaapi.add_menu_item("Debugger/^ Rev to cursor", "Reverse to text segment", None, 1, isim.revToText, None)
    idaapi.add_menu_item("Debugger/^ Rev to cursor", "Exit maze", None, 1, isim.exitMaze, None)

    idaapi.add_menu_item("Debugger/O Run to/", "Run to connect", None, 1, isim.runToConnect, None)
    idaapi.add_menu_item("Debugger/O Run to/", "Run to accept", None, 1, isim.runToAccept, None)
    idaapi.add_menu_item("Debugger/O Run to/", "Run to bind", None, 1, isim.runToBind, None)
    idaapi.add_menu_item("Debugger/O Run to/", "Run to open", None, 1, isim.runToOpen, None)
    idaapi.add_menu_item("Debugger/^ Rev to cursor", "Watch data read", None, 1, isim.watchData, None)
    idaapi.add_menu_item("Debugger/O Run to/", "Run to IO", None, 1, isim.runToIO, None)
    idaapi.add_menu_item("Debugger/^ Rev to cursor", "Stack trace", None, 1, isim.updateStackTrace, None)
    idaapi.add_menu_item("Debugger/^ Rev to cursor", "Show cycle", None, 1, isim.showCycle, None)

    idaapi.CompileLine('static key_alt_shift_n() { RunPythonStatement("nameSysCalls()"); }')
    AddHotkey("Alt+Shift+n", 'key_alt_shift_n')
    
    idaapi.CompileLine('static key_alt_b() { RunPythonStatement("isim.rebuildBookmarkView()"); }')
    AddHotkey("Alt+k", 'key_alt_b')
    idaapi.add_menu_item("View/Open subviews/Hex dump", "View bookmark window", "Alt+b", 1, isim.rebuildBookmarkView, None)
    idaapi.add_menu_item("View/Open subviews/Hex dump", "View stack trace window", None, 1, isim.rebuildStackTrace, None)

    idaapi.CompileLine('static key_alt_shift_b() { RunPythonStatement("isim.revBlock()"); }')
    AddHotkey("Alt+Shift+b", 'key_alt_shift_b')
    idaapi.add_menu_item("Debugger/^ Rev to cursor", "Reverse to previous block", "Alt+Shift+b", 1, isim.revBlock, None)
    
    idaapi.CompileLine('static key_alt_shift_q() { RunPythonStatement("isim.exitIda()"); }')
    AddHotkey("Alt+Shift+q", 'key_alt_shift_q')
    idaapi.add_menu_item("Debugger/Terminate process", "Exit CGC Ida Client", "Alt+Shift+q", 1, isim.exitIda, None)

    idaapi.add_menu_item("Debugger/Terminate process", "Re-synch with server", "", 1, isim.resynch, None)
    #idaapi.add_menu_item("Debugger/Terminate process", "refresh bookmarks", "", 1, refreshBookmarks, None)

    idaapi.CompileLine('static key_alt_shift_g() { RunPythonStatement("generateSignatures()"); }')
    AddHotkey("Alt+Shift+g", 'key_alt_shift_g')
    idaapi.add_menu_item("Debugger/Terminate process", "Generate function signatures", "Alt+Shift+g", 1, generateSignatures, None)

    idaapi.CompileLine('static key_alt_shift_f() { RunPythonStatement("querySignatures()"); }')
    AddHotkey("Alt+Shift+f", 'key_alt_shift_f')
    idaapi.add_menu_item("Debugger/Terminate process", "Apply function signatures", "Alt+Shift+f", 1, querySignatures, None)

    idaapi.CompileLine('static key_alt_shift_y() { RunPythonStatement("isim.signalClient()"); }')
    AddHotkey("Alt+Shift+y", 'key_alt_shift_y')

    idaapi.CompileLine('static key_alt_shift_w() { RunPythonStatement("isim.writeWord()"); }')
    AddHotkey("Alt+Shift+w", 'key_alt_shift_w')
    idaapi.add_menu_item("Debugger/Terminate process", "Write word to memory", "Alt+Shift+w", 1, isim.writeWord, None)
    '''

def nameSysCalls(bail=False):
    print('in nameSysCalls assign names to sys calls')
    start = LocByName("_start")
    
    main = 0
    
    for x in XrefsFrom(start):
       if x.type == fl_CN:
          MakeNameEx(x.to, "main", 0)
          main = x.to
          break
    
    f = GetFunctionAttr(start, FUNCATTR_END)
    
    types = []
    
    types.append(ParseType("void __cdecl _terminate(int exitCode);", 0))
    types.append(ParseType("int __cdecl transmit(int fd, const void *buf, size_t count, size_t *tx_bytes);", 0))
    types.append(ParseType("int __cdecl receive(int fd, void *buf, size_t count, size_t *rx_bytes);", 0))
    types.append(ParseType("int __cdecl fdwait(int nfds, fd_set *readfds, fd_set *writefds, const struct timeval *timeout, int *readyfds);", 0))
    types.append(ParseType("int __cdecl allocate(size_t length, int is_X, void **addr);", 0))
    types.append(ParseType("int __cdecl deallocate(void *addr, size_t length);", 0))
    types.append(ParseType("int __cdecl random(void *buf, size_t count, size_t *rnd_bytes);", 0))

    comms = []
    comms.append("DECREE terminate")
    comms.append("DECREE transmit")
    comms.append("DECREE receive")
    comms.append("DECREE fdwait")
    comms.append("DECREE allocate")
    comms.append("DECREE deallocate")
    comms.append("DECREE random")
    
    names = ["_terminate", "transmit", "receive", "fdwait", "allocate", "deallocate", "random"]
    for i in range(7):
       if i == 1:
          f += 2
       MakeCode(f)
       MakeFunction(f, idaapi.BADADDR)
       try:
           MakeNameEx(f, names[i], 0)
           ApplyType(f, types[i], 0)
       except:
           print('some trouble in MakeNameEx or ApplyType for %s, f is %d' % (names[i], f))
           pass
       end = GetFunctionAttr(f, FUNCATTR_END)
       got_int = False
       if (end - f) > 20000 and bail:
           print('function too big, 0x%x to 0x%x, skipping' % (f, end)) 
           continue
       while not got_int and f < end:
           f = NextAddr(f)
           if GetMnem(f) == "int":
               try:
                   MakeComm(f, comms[i]) 
               except:
                   pass
               got_int = True
       f = end
   
def checkHelp():
    pref_file = None
    if os.path.exists("prefs.txt"):
        pref_file = open("prefs.txt", 'r')
    if pref_file is None or "no_help" not in pref_file.read():
        if showHelp(True):
            print("user said don't show help at startup")
            if pref_file is not None:
                pref_file.close()
            pref_file = open("prefs.txt", 'a')
            pref_file.write("no_help")
            pref_file.close()


class RunToConnectHandler(idaapi.action_handler_t):
    def __init__(self):
        idaapi.action_handler_t.__init__(self)

    # Say hello when invoked.
    def activate(self, ctx):
        print("Hello!")
        return 1

    # This action is always available.
    def update(self, ctx):
        return idaapi.AST_ENABLE_ALWAYS



def RESimClient(re_hooks=None, dbg_hooks=None, idb_hooks=None):
    #Wait() 
    ida_dbg.wait_for_next_event(idc.WFNE_ANY, -1)
    print('back from dbg wait')
    reg_list = idautils.GetRegisterList()
    kernel_base =  0xc0000000
    info = idaapi.get_inf_structure()
    if info.is_64bit():
        print('64-bit')
        kernel_base = 0xFFFFFFFF00000000
    else:
        print('32-bit')
    idc.refresh_lists()
    idc.auto_wait()
    

    bookmark_view = bookmarkView.bookmarkView()
    stack_trace = stackTrace.StackTrace()
    data_watch = dataWatch.DataWatch()
    branch_not_taken = branchNotTaken.BranchNotTaken()
    write_watch = writeWatch.WriteWatch()
    #print('back from init bookmarkView')
    keymap_done = False
    #primePump()
    #nameSysCalls(True)
    #print('back from nameSysCalls')
    #print('now create bookmark_view')
    isim = idaSIM.IdaSIM(stack_trace, bookmark_view, data_watch, branch_not_taken, write_watch, kernel_base, reg_list)

    idaversion.grab_focus('Stack view')
    bm_title = "Bookmarks"
    bookmark_view.Create(isim, bm_title)
    idaversion.grab_focus(bm_title)
    bookmark_view.register()
    bookmark_list = bookmark_view.updateBookmarkView()
    if bookmark_list is not None:
        for bm in bookmark_list:
            if 'nox' in bm:
                eip_str = getTagValue(bm, 'nox')
                eip = int(eip_str, 16)
                idaversion.make_code(eip) 

    idaversion.grab_focus(bm_title)
    st_title = 'stack trace'
    stack_trace.Create(isim, st_title)
    idaversion.grab_focus(st_title)
    stack_trace.register()

    idaversion.grab_focus(st_title)
    dw_title = 'data watch'
    data_watch.Create(isim, dw_title)
    idaversion.grab_focus(dw_title)
    data_watch.register()

    bnt_title = 'BNT'
    idaversion.grab_focus(dw_title)
    branch_not_taken.Create(isim, bnt_title)
    idaversion.grab_focus(bnt_title)
    branch_not_taken.register()
    #branch_not_taken.updateList()
  
    idaversion.grab_focus(bnt_title)
    ww_title = 'write watch' 
    write_watch.Create(isim, ww_title)
    idaversion.grab_focus(ww_title)
    write_watch.register()


    reHooks.register(isim)
    re_hooks.setIdaSim(isim)

    dbg_hooks.setRESim(isim)
    idb_hooks.setRESim(isim)
    

    if not keymap_done:
        doKeyMap(isim)
        print('dbg %r' % idaapi.dbg_is_loaded())
    
        isim.showSimicsMessage()
    
        idaversion.refresh_debugger_memory()
    #checkHelp()
    isim.recordText()
    isim.showSimicsMessage()
    if not isim.just_debug:
        # first origin is sometimes off, call twice.
        #goToOrigin()
        pass
    idaversion.batch(0)
    #isim.resynch()
    print('IDA SDK VERSION: %d' %  idaapi.IDA_SDK_VERSION)
    print('RESim IDA Client Version 1.2a')

if __name__ == "__main__":
    #Hooks must be done in main.  Also see runsFirst.py
    idb_hooks = idbHooks.IDBHooks()
    idb_hooks.hook()
    re_hooks = reHooks.Hooks()
    dbg_hooks = dbgHooks.DBGHooks()
    dbg_hooks.setIdbHooks(idb_hooks)
    dbg_hooks.setReHooks(re_hooks)
    re_hooks.hook()
    dbg_hooks.hook()
    RESimClient(re_hooks=re_hooks, dbg_hooks=dbg_hooks, idb_hooks=idb_hooks)
