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
'''
   Manage instances of the Syscall modules in different contexts.
'''
import syscall
import winSyscall
import vxKSyscall
import vxKCallExit
LAST_PARAM = 1
REDO_SYSCALLS = 2
REMOVED_OK = 3
class SyscallInstance():
    ''' Track Syscall module instances '''
    def __init__(self, name, call_names, syscall, call_params, lgr):
        ''' most recently assigned name, do not read too much into it'''
        self.name = name
        ''' the list of syscall names handled by the syscall instance '''
        self.call_names = call_names
        ''' the syscall instance '''
        self.syscall = syscall
        ''' map which system calls apply to each parameter name 
            This is intended for use in removing system call parameters and system calls.
        '''
        self.param_call_list = {}
        for param in call_params:
            self.param_call_list[param.name] = call_names
        self.lgr = lgr

    def toString(self):
        retval = 'Name: %s  calls: %s' % (self.name, str(self.call_names))
        return retval

    def hasCall(self, name):
        if name in self.call_names:
            return True
        else:
            return False

    def callsMatch(self, call_list):
        retval = True
        if len(call_list) == len(self.call_names):
            for call in call_list:
                if call not in self.call_names:
                    retval = False
                    break
        else:
            retval = False
        return retval

    def hasAllCalls(self, call_list):
        retval = True
        if len(call_list) <= len(self.call_names):
            for call in call_list:
                if call not in self.call_names:
                    retval = False
                    break
        else:
            retval = False
        return retval

    def hasParamName(self, param_name):
        retval = self.syscall.hasCallParam(param_name)
        return retval

    def stopTrace(self, immediate=False):
        self.syscall.stopTrace(immediate=immediate)

    def addCallParams(self, call_params, call_names):
        for call in call_names:
            if call not in self.call_names:
                self.call_names.append(call)
        ''' all of the given call parameters apply to each of the given call names '''
        for param in call_params:
            if param.name in self.param_call_list:
                # don't error if the param was queued up to be removed from the syscall
                if not self.syscall.rmRmParam(param.name):
                    self.lgr.error('syscallManager SyscallInstance addCallParams, %s already in list' % param.name)
            else:
                self.param_call_list[param.name] = call_names
                self.lgr.debug('syscallManager SyscallInstance %s addCallParams set self.param_call_list[%s] to %s' % (self.name, param.name, call_names))
        self.syscall.addCallParams(call_params)

    def rmCallParam(self, call_param_name, immediate=False):
        self.lgr.debug('syscallManager SyscallInstance %s rmCallParam param %s' % (self.name, call_param_name))
        retval = REMOVED_OK
        self.syscall.rmCallParamName(call_param_name)
        if len(self.param_call_list) == 1:
            if call_param_name in self.param_call_list:
                self.syscall.stopTrace(immediate=immediate)
                retval = LAST_PARAM
                self.lgr.debug('syscallManager SyscallInstance %s rmCallParam param %s, last one, stop trace' % (self.name, call_param_name))
            else:
                self.lgr.error('syscallManager rmCallParam list param is not given %s' % call_param_name)
                return None
        else:
            ''' see if other call params include all of this params syscalls, if not, will need to recreate '''

            self.lgr.debug('syscallManager SyscallInstance %s rmCallParam param %s, other parames, check em out' % (self.name, call_param_name))
            got_all = True
            for call in self.param_call_list[call_param_name]:
                got_one = False
                for param_name in self.param_call_list:
                    if param_name == call_param_name:
                        continue
                    if call in self.param_call_list[param_name]:
                        got__one = True
                        break
                if not got_one:
                    retval = REDO_SYSCALLS
                    self.call_names.remove(call)
        del self.param_call_list[call_param_name]
        return retval

    def hasOtherCalls(self, call_param_name):
        retval = []
        for param_name in self.param_call_list:
            if param_name == call_param_name:
                continue
            for call in self.param_call_list[param_name]:
                if call_param_name not in self.param_call_list or call not in self.param_call_list[call_param_name]:
                    if call not in retval:
                        retval.append(call)
        return retval

class SyscallManager():
    def __init__(self, top, cpu, cell_name, param, mem_utils, task_utils, context_manager, traceProcs, sharedSyscall, lgr, 
                   traceMgr, soMap, dataWatch, compat32, targetFS, os_type):
        self.top = top
        self.param = param
        self.cpu = cpu
        self.cell_name = cell_name
        self.task_utils = task_utils
        self.mem_utils = mem_utils
        self.context_manager = context_manager
        ''' TBD maybe traceProcs passed in for each instance if it is to be traced? or other mechanism '''
        self.traceProcs = traceProcs
        self.lgr = lgr
        self.traceMgr = traceMgr
        self.dataWatch = dataWatch
        self.soMap = soMap
        if self.soMap is None:
            self.lgr.error('SOMap is none in syscall manager')
        self.targetFS = targetFS
        self.compat32 = compat32
        self.os_type = os_type

        self.syscall_dict = {}
        self.trace_all = {}
        if self.top.isVxDKM(target=cell_name):
            self.sharedSyscall = vxKCallExit.VxKCallExit(top, cpu, cell_name, mem_utils, task_utils, soMap, self.traceMgr, self.dataWatch, lgr)
        else:
            self.sharedSyscall = sharedSyscall

    def watchAllSyscalls(self, context, name, linger=False, background=False, flist=None, callback=None, compat32=None, stop_on_call=False, 
                         trace=False, binders=None, connectors=None, record_fd=False, swapper_ok=False, netInfo=None, call_params_list=[]):
   
        if compat32 is None:
            compat32 = self.compat32

        if context is None:
            context = self.getDebugContextName()
            
        cell = self.context_manager.getCellFromContext(context)
        self.lgr.debug('syscallManager watchAllSyscalls name %s context %s' % (name, context))
        # gather parameters first and stuff them into traceall
        removed_params = self.rmSyscallByContext(context)
        if self.top.isWindows(self.cell_name):
            retval = winSyscall.WinSyscall(self.top, self.cell_name, cell, self.param, self.mem_utils, 
                               self.task_utils, self.context_manager, self.traceProcs, self.sharedSyscall, 
                               self.lgr, self.traceMgr, self.dataWatch, call_list=None, call_params=[], targetFS=self.targetFS, linger=linger, 
                               background=background, name=name, flist_in=flist, callback=callback, 
                               stop_on_call=stop_on_call, trace=trace, soMap=self.soMap,
                               record_fd=record_fd, swapper_ok=swapper_ok)
        elif self.top.isVxDKM(target = self.cell_name):
            retval = vxKSyscall.VxKSyscall(self.top, self.cpu, self.cell_name, self.mem_utils, self.task_utils, self.soMap, self.sharedSyscall, self.traceMgr, 
                         self.context_manager, self.lgr, name=name, flist_in=flist, linger=linger)
        else:
            retval = syscall.Syscall(self.top, self.cell_name, cell, self.param, self.mem_utils, 
                               self.task_utils, self.context_manager, self.traceProcs, self.sharedSyscall, 
                               self.lgr, self.traceMgr, call_list=None, call_params=call_params_list, targetFS=self.targetFS, linger=linger, 
                               background=background, name=name, flist_in=flist, callback=callback, compat32=compat32, 
                               stop_on_call=stop_on_call, trace=trace, binders=binders, connectors=connectors, soMap=self.soMap,
                               netInfo=netInfo, record_fd=record_fd, swapper_ok=swapper_ok)
        retval.addCallParams(removed_params)
        self.trace_all[context] = retval
        return retval

    def getDebugContextName(self):
        ''' return the debugging context if debugging.  Otherwise return default context '''
        debug_tid, debug_cpu = self.context_manager.getDebugTid()
        if debug_tid is not None:
            context = self.context_manager.getRESimContextName()
        else:
            context = self.context_manager.getDefaultContextName()
        return context 

    def watchSyscall(self, context, call_list, call_params_list, name, linger=False, background=False, flist=None, 
                     callback=None, compat32=False, stop_on_call=False, skip_and_mail=True, kbuffer=None, trace=False):
        ''' Create a syscall instance.  Intended for use by other modules, not by this module.
            Assumes all of the call_params have the same call parameter name for purposes of managing the
            call instances, e.g, an open watched for a dmod and a SO mapping.
        '''
        # TBD callback should be per call parameter, not per syscall instance
        self.lgr.debug('syscallManager watchSyscall given context %s name: %s call_list %s' % (context, name, str(call_list)))
        retval = None 
        if context is None:
            # NOTE may return default context
            context = self.getDebugContextName()
            self.lgr.debug('syscallManager watchSyscall given context was none, now set to %s' % context)

        cell = self.context_manager.getCellFromContext(context)

        if len(call_params_list) == 0:
            ''' For use in deleting syscall instances '''
            dumb_param = syscall.CallParams(name, None, None)
            call_params_list.append(dumb_param)
            self.lgr.debug('syscallManager watchSyscall context %s, added dummy parameter with name %s' % (context, name))

        call_instance = self.findCalls(call_list, context)
        if call_instance is None:
            if context in self.trace_all:
                retval = self.trace_all[context] 
                self.lgr.debug('syscallManager watchSyscall found traceAll, add params to that.')
                retval.addCallParams(call_params_list)
            else:
                self.lgr.debug('syscallManager watchSyscall context %s, create new instance for %s, cell %s' % (context, name, cell))
                if self.top.isWindows(self.cell_name):
                    retval = winSyscall.WinSyscall(self.top, self.cell_name, cell, self.param, self.mem_utils, 
                                   self.task_utils, self.context_manager, self.traceProcs, self.sharedSyscall, self.lgr, self.traceMgr,
                                   self.dataWatch, call_list=call_list, call_params=call_params_list, targetFS=self.targetFS, linger=linger, 
                                   background=background, name=name, flist_in=flist, callback=callback, soMap=self.soMap, 
                                   stop_on_call=stop_on_call, skip_and_mail=skip_and_mail, kbuffer=kbuffer, trace=trace)
                elif self.top.isVxDKM(target = self.cell_name):
                    # hack to hack ioctl for old binaries
                    if 'ioctl' not in call_list:
                        call_list.append('ioctl')
                    retval = vxKSyscall.VxKSyscall(self.top, self.cpu, self.cell_name, self.mem_utils, self.task_utils, self.soMap, 
                                 self.sharedSyscall, self.traceMgr, self.context_manager, self.lgr, call_list=call_list, call_params=call_params_list, 
                                 flist_in=flist, name=name, linger=linger)
                else:
                    retval = syscall.Syscall(self.top, self.cell_name, cell, self.param, self.mem_utils, 
                                   self.task_utils, self.context_manager, self.traceProcs, self.sharedSyscall, self.lgr, self.traceMgr,
                                   call_list=call_list, call_params=call_params_list, targetFS=self.targetFS, linger=linger, 
                                   background=background, name=name, flist_in=flist, callback=callback, compat32=compat32, soMap=self.soMap, 
                                   stop_on_call=stop_on_call, skip_and_mail=skip_and_mail, kbuffer=kbuffer, trace=trace)
                ''' will have at least one call parameter, perhaps the dummy. '''
                self.lgr.debug('syscallManager watchSyscall context %s, created new instance for %s' % (context, name))
                call_instance = SyscallInstance(name, call_list, retval, call_params_list, self.lgr)
                if context not in self.syscall_dict:
                    self.lgr.debug('syscalManager added context %s to syscall_dict' % context)
                    self.syscall_dict[context] = {}
                self.syscall_dict[context][name] = call_instance
        else:
            if call_instance.callsMatch(call_list) or call_instance.hasAllCalls(call_list):
                call_instance.addCallParams(call_params_list, call_list)
                self.lgr.debug('syscallManager watchSyscall, did not create new instance for %s, added params to %s' % (name, call_instance.name))
                retval = call_instance.syscall
                retval.addCallParams(call_params_list)
                params_now = retval.getCallParams()
                self.lgr.debug('syscallManager after added params now:')
                for p in params_now:
                    self.lgr.debug('\t\t%s' % p.name)
            else:
                self.lgr.debug('syscallManager watchSyscall given call list has some calls that are and some that are not present in existing calls.  Delete and recreate. given %s' % str(call_list))

                ''' Existing call params to pass to the new syscall AFTER it is constructed.  Will be constructed with just the new params
                    but with the expanded call list
                '''
                old_call_params = list(call_instance.syscall.getCallParams())

                existing_call_list = call_instance.call_names
                ''' Call list to pass to new syscall constructor '''
                new_call_list = list(call_list)
                for call in existing_call_list:
                    if call not in new_call_list:
                        new_call_list.append(call)

                if kbuffer is None:
                    kbuffer = call_instance.syscall.kbuffer
                if callback is not None and call_instance.syscall.callback is not None and callback != call_instance.syscall.callback:
                    self.lgr.error('syscallManager watchSyscall conflicting callbacks')
                if callback is None:
                    callback = call_instance.syscall.callback

                ''' Map of calls for each parameter from previous instance 
                    Must maintain so we can manage parameter (syscall) deletion
                '''
                existing_param_call_list = call_instance.param_call_list 
               
                ''' Remove the old system call HAPS and the instance'''
                call_instance.syscall.stopTrace(immediate=True)
                del self.syscall_dict[context][call_instance.name]
                self.lgr.debug('syscallManager deleted syscall instance for syscall name %s, will replace with %s.  The syscall_dict[context] now has %d items' % (call_instance.syscall.name, name, len(self.syscall_dict[context])))
                for dict_name in self.syscall_dict[context]:
                    self.lgr.debug('\t dict item: syscallManager dict name %s syscall name %s' % (dict_name, self.syscall_dict[context][dict_name].syscall.name))

                ''' TBD what about flist and stop action?'''
                if self.top.isWindows(self.cell_name):
                    retval = winSyscall.WinSyscall(self.top, self.cell_name, cell, self.param, self.mem_utils, 
                               self.task_utils, self.context_manager, self.traceProcs, self.sharedSyscall, self.lgr, self.traceMgr, self.dataWatch,
                               call_list=new_call_list, call_params=call_params_list, targetFS=self.targetFS, linger=linger, soMap=self.soMap,
                               background=background, name=name, flist_in=flist, callback=callback, stop_on_call=stop_on_call, kbuffer=kbuffer)
                elif self.top.isVxDKM(target = self.cell_name):
                    retval = vxKSyscall.VxKSyscall(self.top, self.cpu, self.cell_name, self.mem_utils, self.task_utils, self.soMap, self.sharedSyscall, 
                                 self.traceMgr, self.context_manager, self.lgr, call_list=new_call_list, call_param=call_params_list, name=name, flist_in=flist, linger=linger)
                else:
                    retval = syscall.Syscall(self.top, self.cell_name, cell, self.param, self.mem_utils, 
                               self.task_utils, self.context_manager, self.traceProcs, self.sharedSyscall, self.lgr, self.traceMgr,
                               call_list=new_call_list, call_params=call_params_list, targetFS=self.targetFS, linger=linger, soMap=self.soMap,
                               background=background, name=name, flist_in=flist, callback=callback, compat32=compat32, stop_on_call=stop_on_call, kbuffer=kbuffer)

                new_call_instance = SyscallInstance(name, new_call_list, retval, call_params_list, self.lgr)
                new_call_instance.syscall = retval
                ''' add back old params and corresponding call lists'''
                for param in old_call_params:
                    new_call_instance.addCallParams([param], existing_param_call_list[param.name])
                   
                self.syscall_dict[context][name] = new_call_instance
                self.lgr.debug('syscallManager watchSyscall replaced old syscall, call_list and params for call instance %s syscall name %s' % (new_call_instance.name, 
                   name))
 
        return retval

    def rmSyscall(self, call_param_name, immediate=False, context=None, rm_all=False):
        ''' Find and remove the syscall having the given call parameters name assuming that is the only
            (remaining) call parameter for the system call.
            Otherwise, remove the call parameter.  If the call parameter includes syscalls that are not
            part of any other call parameter, remove the instance and recreate it.
        '''
        if context is None:
            context = self.getDebugContextName()
        call_instance = self.findInstanceByParams(call_param_name, context)
        if call_instance is None:
            self.lgr.debug('syscallManager rmSyscall did not find syscall instance with context %s and param name %s' % (context, call_param_name))
        elif rm_all:
            call_instance.stopTrace(immediate=immediate) 
            del self.syscall_dict[context][call_instance.name]
            self.lgr.debug('syscallManager rmSyscall context %s.  Remove all set.   Param %s' % (context, call_param_name))
        else:
            self.lgr.debug('syscallManager rmSyscall call_param_name %s context %s immediate %r' % (call_param_name, context, immediate))

            result = call_instance.rmCallParam(call_param_name, immediate=immediate)
            if result is None:
                return
            elif result == REMOVED_OK:
                self.lgr.debug('syscallManager rmSyscall removed param %s without otherwise changing the syscall.' % call_param_name)
            elif result == LAST_PARAM:
                self.lgr.debug('syscallManager rmSyscall removed param %s was last param, remove instance.' % call_param_name)
                del self.syscall_dict[context][call_instance.name]
            elif result == REDO_SYSCALLS:
                self.lgr.debug('syscallManager rmSyscall redo syscalls after removing %s' % call_param_name)
                if self.top.isWindows(self.cell_name):
                    compat32 = False
                else:
                    compat32 = call_instance.syscall.compat32
                ''' 
                    Remaining call params from old instance
                '''
                old_call_params = list(call_instance.syscall.getCallParams())

                ''' Map of calls for each parameter from instance 
                    after param had been removed
                '''
                old_param_call_list = call_instance.param_call_list 
                ''' Recreate a new call list to pass to syscall constructor'''
                new_call_list = []
                for param_name in old_param_call_list:
                    for call in old_param_call_list[param_name]:
                        if call not in new_call_list:
                            new_call_list.append(call)
                # TBD allocate these to call parameters
                kbuffer = call_instance.syscall.kbuffer
                linger = call_instance.syscall.linger
                background = call_instance.syscall.background
                stop_on_call = call_instance.syscall.stop_on_call
                flist = call_instance.syscall.flist_in
                callback = call_instance.syscall.callback
               
                ''' Remove the old system call HAPS and the instance'''
                call_instance.syscall.stopTrace(immediate=True)
                del self.syscall_dict[context][call_instance.name]
                name = call_instance.name
                self.lgr.debug('syscallManager rmSyscall deleted syscall instance for syscall name %s The syscall_dict[context] now has %d items' % (call_instance.syscall.name, len(self.syscall_dict[context])))
                for dict_name in self.syscall_dict[context]:
                    self.lgr.debug('\t dict item: syscallManager dict name %s syscall name %s' % (dict_name, self.syscall_dict[context][dict_name].syscall.name))

                cell = self.context_manager.getCellFromContext(context)
                ''' TBD what about flist and stop action?'''
                ''' Recreate with empty call params '''
                if self.top.isWindows(self.cell_name):
                    retval = winSyscall.WinSyscall(self.top, self.cell_name, cell, self.param, self.mem_utils, 
                               self.task_utils, self.context_manager, self.traceProcs, self.sharedSyscall, self.lgr, self.traceMgr, self.dataWatch,
                               call_list=new_call_list, call_params=[], targetFS=self.targetFS, linger=linger, soMap=self.soMap,
                               background=background, name=name, flist_in=flist, callback=callback, stop_on_call=stop_on_call, kbuffer=kbuffer)
                else:
                    retval = syscall.Syscall(self.top, self.cell_name, cell, self.param, self.mem_utils, 
                               self.task_utils, self.context_manager, self.traceProcs, self.sharedSyscall, self.lgr, self.traceMgr,
                               call_list=new_call_list, call_params=[], targetFS=self.targetFS, linger=linger, soMap=self.soMap,
                               background=background, name=name, flist_in=flist, callback=callback, compat32=compat32, stop_on_call=stop_on_call, kbuffer=kbuffer)
                self.lgr.debug('syscallManager rmSyscall created syscall with call list %s' % str(new_call_list))

                new_call_instance = SyscallInstance(name, new_call_list, retval, [], self.lgr)
                new_call_instance.syscall = retval
                ''' add back old params and corresponding call lists'''
                for param in old_call_params:
                    self.lgr.debug('syscallManager rmSyscall add params for parm name %s' % param.name)
                    new_call_instance.addCallParams([param], old_param_call_list[param.name])
                   
                self.syscall_dict[context][name] = new_call_instance
                self.lgr.debug('syscallManager watchSyscall replaced old syscall, call_list and params for call instance %s syscall name %s' % (new_call_instance.name, 
                   name))


    def findInstanceByParams(self, call_param_name, context):
        ''' Return the Syscallinstance that contains params having the given name.   Assumes only one. '''
       
        retval = None
        if context in self.syscall_dict:
            for instance_name in self.syscall_dict[context]:
                call_instance = self.syscall_dict[context][instance_name]
                if call_instance.hasParamName(call_param_name):
                    retval = call_instance
                    break
        return retval 

    def findCalls(self, call_list, context):
        ''' Return the Syscallinstance that contains at least one call in the given call list if any.
            Favor the the one with the most matches.
        '''
        # TBD does not handle case where on in one and another in another
        self.lgr.debug('syscallManager findCalls for given context %s search for call list: %s' % (context, str(call_list)))   
        retval = None
        best_count = 0
        if context in self.syscall_dict:
            for instance_name in self.syscall_dict[context]:
                call_instance = self.syscall_dict[context][instance_name]
                self.lgr.debug('syscallManager findCalls check instance %s call names: %s' % (instance_name, str(call_instance.call_names)))
                match_count = 0
                for call in call_list:
                    if call_instance.hasCall(call):
                        match_count = match_count + 1
                        self.lgr.debug('\tsyscallManager instance %s had call %s' % (call_instance.name, call))
                if match_count > best_count:
                    retval = call_instance
        else:
            self.lgr.debug('syscallManager findCalls context %s not in syscall_dict' % context)
        return retval 

    def rmAllSyscalls(self):
        self.lgr.debug('syscallManager rmAllSyscalls')
        retval = False
        rm_list = {}
        for context in self.syscall_dict:
            rm_list[context] = []
            for instance_name in self.syscall_dict[context]:
                rm_list[context].append(instance_name)
                self.syscall_dict[context][instance_name].stopTrace()
                self.lgr.debug('syscallManager rmAllSyscalls remove %s' % instance_name)
                retval = True
        for context in rm_list:
            for instance_name in rm_list[context]:
                del self.syscall_dict[context][instance_name]
            del self.syscall_dict[context]

        rm_context = []
        for context in self.trace_all:
            self.lgr.debug('syscallManager rmAllSyscalls remove trace_all for context %s' % context)
            self.trace_all[context].stopTrace()
            rm_context.append(context)
            retval = True
        for context in rm_context:
            del self.trace_all[context]
        return retval
        
    def rmSyscallByContext(self, context):
        self.lgr.debug('syscallManager rmSyscallByContext')
        retval = []
        rm_list = []
        if context in self.syscall_dict:
            for instance_name in self.syscall_dict[context]:
                rm_list.append(instance_name)
                
                params = self.syscall_dict[context][instance_name].syscall.getCallParams()
                if params is not None:
                    for p in params:
                        retval.append(p)
                    self.syscall_dict[context][instance_name].stopTrace()
                    self.lgr.debug('syscallManager mrSyscallByContext remove %s' % instance_name)

            for instance_name in rm_list:
                del self.syscall_dict[context][instance_name]
            del self.syscall_dict[context]

        if context in self.trace_all:
            self.lgr.debug('syscallManager mrSyscallByContext remove trace_all for context %s' % context)
            self.trace_all[context].stopTrace()
            del self.trace_all[context]
        return retval

    #def stopTrace(self, param_name):

    def remainingCallTraces(self, exception=None, context=None):
        ''' Are there any call traces remaining, if so return True
            unless the only remaining trace is named by the given exception '''
            
        retval = False
        if context is None:
            context = self.getDebugContextName()
        if exception is None:
            if context in self.syscall_dict and len(self.syscall_dict[context])>0:
                retval = True 
        else:
            if context in self.syscall_dict:
                if len(self.syscall_dict[context]) == 1:
                    instance = self.findCalls([exception], context)
                    if instance is None:
                        ''' only one, but not the exception '''
                        retval = True
                elif len(self.syscall_dict[context]) > 1:
                        retval = True
                   
        return retval 

    def showSyscalls(self):
        for context in self.syscall_dict:
            print('\tcontext: %s' % context)
            for instance in self.syscall_dict[context]:
                out_string = self.syscall_dict[context][instance].toString()
                print('\t\t%s' % out_string)

    def getReadAddr(self):
        ''' Used by writeData to track data read from kernel. ''' 
        retval = None
        length = None 
        callnum = self.mem_utils.getCallNum(self.cpu)
        callname = self.task_utils.syscallName(callnum, self.compat32) 
        if callname is None:
            self.lgr.debug('getReadAddr bad call number %d' % callnum)
            return None, None
        frame = self.task_utils.frameFromRegs()
        if self.top.isWindows(self.cell_name):
            tid = self.top.getTID(target=self.cell_name)
            word_size = 8 # default to 8 for 64 bit unless 
            if self.soMap.getMachineSize(tid) == 32: # we find out otherwise
                word_size = 4
            retval = winSyscall.paramOffPtrUtil(7, [0, word_size], frame, word_size, self.cpu, self.mem_utils, self.lgr)
            value = winSyscall.paramOffPtrUtil(7, [0, 0], frame, word_size, self.cpu, self.mem_utils, self.lgr) 
            if value is not None:
                length = value & 0xFFFFFFFF
        else:
            if callname in ['read', 'recv', 'recfrom']:
                retval = frame['param2']
                length = frame['param3']
            elif callname == 'socketcall':
                retval = self.mem_utils.readWord32(self.cpu, frame['param2']+16)
                length = self.mem_utils.readWord32(self.cpu, frame['param2']+20)
       
        return retval, length

    def rmAllDmods(self):
        self.lgr.debug('syscallManager rmAllDmods')
        rm_dict = {}
        for context in self.syscall_dict:
            for instance in self.syscall_dict[context]:
                call_parameters = self.syscall_dict[context][instance].syscall.getCallParams()
                params_copy = list(call_parameters)

                for call_param in params_copy:
                    if call_param.match_param.__class__.__name__ == 'Dmod':
                        self.lgr.debug('syscallManager rmDmods, removing dmod %s' % call_param.match_param.path)
                        if context not in rm_dict:
                            rm_dict[context] = {}
                        if instance not in rm_dict[context]:
                            rm_dict[context][instance] = []
                        rm_dict[context][instance].append(call_param)

        for context in rm_dict:
            for instance in rm_dict[context]:
                for call_param in rm_dict[context][instance]:
                    self.syscall_dict[context][instance].syscall.rmCallParam(call_param, quiet=True)
                call_parameters = self.syscall_dict[context][instance].syscall.getCallParams()
                if len(call_parameters) == 0:
                    self.lgr.debug('syscallManager rmAllDmods, no more call_params, remove syscall')
                    self.syscall_dict[context][instance].stopTrace()
                    del self.syscall_dict[context][instance]

    def showDmods(self):
        self.lgr.debug('syscallManager showDmods')
        for context in self.syscall_dict:
            for instance in self.syscall_dict[context]:
                call_parameters = self.syscall_dict[context][instance].syscall.getCallParams()
                for call_param in call_parameters:
                    if call_param.match_param.__class__.__name__ == 'Dmod':
                        print('context %s instance %s param %s %s' % (context, instance, call_param.name, call_param.match_param.toString()))

    def getDmodPaths(self):
        self.lgr.debug('syscallManager getDmodPaths')
        dmod_list = []
        for context in self.syscall_dict:
            for instance in self.syscall_dict[context]:
                call_parameters = self.syscall_dict[context][instance].syscall.getCallParams()
                for call_param in call_parameters:
                    if call_param.match_param.__class__.__name__ == 'Dmod':
                        path = call_param.match_param.getPath()
                        if path not in dmod_list:
                            dmod_list.append(path)
        return dmod_list
