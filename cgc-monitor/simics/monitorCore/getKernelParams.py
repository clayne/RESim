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
   Generates a RESim parameter file.  Intended to be invoked by launchKparam.py
   See that script for details.
'''
from simics import *
#import linux4_4_32
import linuxParams
import memUtils
import taskUtils
import utils
import kParams
import pickle
class GetKernelParams():
    def __init__(self):
        self.target = os.getenv('RESIM_TARGET')
        print('using target of %s' % self.target)
        self.log_dir = '/tmp'
        self.lgr = utils.getLogger('getKernelParams', self.log_dir)
        self.param = kParams.Kparams()
        self.mem_utils = memUtils.memUtils(4, self.param)
        self.cpu = SIM_current_processor()
        obj = SIM_get_object('viper')
        self.cell = obj.cell_context
        print('current processor %s' % self.cpu.name)
        #self.taskUtils = taskUtils.TaskUtils(self.cpu, self.param, self.mem_utils, self.param.current_task, self.lgr)
        self.hits = []
        self.trecs = []
        self.idle = None
        self.dumb_count = 0
        self.stop_hap = None
        self.mode_hap = None
        self.page_hap = None
        self.prev_instruct = ''
        self.current_task_phys = None
        self.unistd32 = '/mnt/ubuntu_img/linux-2.6.32/linux-2.6.32/arch/x86/include/asm/unistd_32.h'

        self.current_pid = None
 

    def searchCurrentTaskAddr(self, cpu, cur_task, fs=True):
        ''' Look for the Linux data addresses corresponding to the current_task symbol 
            starting at 0xc1000000.  Record each address that contains a match,
            and that list will be reduced later. 
        '''
        #self.run2Kernel(cpu)
        self.lgr.debug('searchCurrentTaskAddr task for task 0x%x fs: %r' % (cur_task, fs))
        start = 0xc1000000
        SIM_run_command('pselect cpu-name = %s' % cpu.name)
        if fs:
            cmd = 'logical-to-physical fs:0x%x' % start
        else:
            cmd = 'logical-to-physical 0x%x' % start
        #print('cmd is %s' % cmd)
        cpl = memUtils.getCPL(cpu)
        #print('cpl is %d' % cpl)
        addr = SIM_run_command(cmd)
        got_count = 0
        offset = 0
        for i in range(14000000):
            val = None
            try:
                val = SIM_read_phys_memory(cpu, addr, 4)
            except:
                pass
            #val = self.mem_utils.readPtr(cpu, addr)
            if val is None:
                self.lgr.error('got None at 0x%x' % addr)
                return 
            if val == cur_task:
                vaddr = start+offset
                self.lgr.debug('got match at addr: 0x%x vaddr: 0x%x' % (addr, vaddr))
                self.hits.append(vaddr)
                got_count += 1
                #break
            if got_count == 9999:
                self.lgr.error('exceeded count')
                break
            #print('got 0x%x from 0x%x' % (val, addr))
            addr += 4
            offset += 4
        self.lgr.debug('final addr is 0x%x num hits %d' % ((start+offset), len(self.hits)))

    def checkHits(self, cur_task):
        ''' look at previously generated list of candidate current_task addresses and remove any
            that do not contain the given cur_task '''
        self.lgr.debug('checkHits cur_task is 0x%x' % cur_task)
        copy_hits = list(self.hits)
        SIM_run_command('pselect cpu-name = %s' % self.cpu.name)
        for hit in copy_hits:
            if self.param.current_task_fs:
                cmd = 'logical-to-physical fs:0x%x' % hit
            else:
                cmd = 'logical-to-physical 0x%x' % hit
            addr = SIM_run_command(cmd)
            val = SIM_read_phys_memory(self.cpu, addr, 4)
            if val != cur_task:
                self.lgr.debug('checkHits hit at 0x%x, removing because cur_task 0x%x does not equal val 0x%x ' % (hit, cur_task, val))
                self.hits.remove(hit)
            
    def getCurrentTaskPtr(self):
        ''' find the current_task record pointer ''' 
        self.idle = None
        from_boot = False
        print('Searching for current_task, this may take a moment...')
        for i in range(900000):
            cpl = memUtils.getCPL(self.cpu)
            if cpl == 0:
                ta = self.mem_utils.getCurrentTask(self.param, self.cpu)
                if ta is None or ta == 0:
                    SIM_run_command('c 5000000')
                    continue 
                else:
                    from_boot = True
                if ta not in self.trecs:
                    if len(self.hits) == 0:
                        self.lgr.debug('getCurrentTaskPtr find current')
                        self.searchCurrentTaskAddr(self.cpu, ta)
                        if not from_boot and (len(self.hits) > 0 and len(self.hits)<3):
                            self.lgr.debug('getCurrentTaskPtr after searchCurrentTaskAdd adding trec 0x%x' % ta)
                            self.trecs.append(ta)
                            ''' maybe older kernel, we assumed those with fs relative will have many hits '''
                            self.hits = []
                            self.lgr.debug('getCurrentTaskPtr set current_task_fs to False')
                            self.param.current_task_fs = False
                            self.searchCurrentTaskAddr(self.cpu, ta, fs=False)
                 
                    else:
                        self.lgr.debug('getCurrentTaskPtr adding trec 0x%x' % ta)
                        self.trecs.append(ta)
                        self.lgr.debug('checkHits with new ta 0x%x' % ta)
                        self.checkHits(ta)

                    if len(self.hits) > 0 and len(self.hits) < 3:
                        for hit in self.hits:
                            self.lgr.debug('hit: 0x%x' % hit)
                        self.param.current_task = self.hits[0]
                        self.lgr.debug('getCurrentTaskPtr remaining hits < 3, assigned 0x%x' % self.hits[0])
                        break
            SIM_run_command('c 5000000')
        if len(self.hits) > 2:
            ''' maybe in tight application loop, assume second to last entry based on observations '''
            self.param.current_task = self.hits[-2]
            self.lgr.debug('assuming 2nd to last for current_task')

    def isThisSwapper(self, task):
        real_parent_offset = 0
        for i in range(800):
            test_task = self.mem_utils.readPtr(self.cpu, task + real_parent_offset)
            test_task1 = self.mem_utils.readPtr(self.cpu, task + real_parent_offset+4)
            if test_task == task and test_task1 == task:
                return real_parent_offset
            else:
                real_parent_offset += 4
        return None

    def isSwapper(self, task): 
        ''' look for what might be a real_parent and subsequent parent pointer fields that point to the
            given task.  if found, assume this is swaper and record those offsets.'''
        #self.lgr.debug('isSwapper check task 0x%x real realparent is 0x%x' % (task, self.real_param.ts_real_parent))
        real_parent_offset = self.isThisSwapper(task)
        if real_parent_offset is not None:
            self.lgr.debug('isSwapper real_parent at 0x%x looks like swapper at 0x%x' % (real_parent_offset, task))
            self.idle = task
            self.param.ts_real_parent = real_parent_offset
            self.param.ts_parent = real_parent_offset + 4
            self.param.ts_children_list_head = real_parent_offset + 8
            self.param.ts_sibling_list_head = real_parent_offset + 16
            self.param.ts_thread_group_list_head = real_parent_offset + 32
        return real_parent_offset
      
    def getInitAlone(self, dumb): 
        self.getInit()
        self.lgr.debug('back from getInit, now call checkTasks')
        self.checkTasks()
        self.lgr.debug('back from checkTasks')
        SIM_run_alone(self.checkKernelEntry, None)

    def swapperStopHap(self, dumb, one, exception, error_string):
        SIM_hap_delete_callback_id("Core_Breakpoint_Memop", self.task_hap)
        SIM_hap_delete_callback_id("Core_Simulation_Stopped", self.stop_hap)
        SIM_run_alone(self.getInitAlone, None)

    def changedThread(self, cpu, third, forth, memory):
        self.lgr.debug('changed thread')
        ''' does the current thread look like swapper? would have consecutive pointers to itself '''
        if self.task_break is None:
            return
        cur_task = SIM_read_phys_memory(self.cpu, self.current_task_phys, 4)
        if cur_task not in self.trecs:
            self.trecs.append(cur_task)
            self.lgr.debug('changedThread try task 0x%x' % cur_task)
            if cur_task != 0 and self.isSwapper(cur_task) is not None:
                self.lgr.debug('changedThread found swapper 0x%x  real_parent %d' % (self.idle, self.param.ts_real_parent))
                SIM_break_simulation('found swapper')
                SIM_delete_breakpoint(self.task_break)
                self.task_break = None 

    
    def runUntilSwapper(self):
        ''' run until it appears that the swapper is running.  Will set self.idle, real_parent, siblings '''
        self.lgr.debug('runUntilSwapper')
        if self.param.current_task is None:
            self.lgr.debug('will get Current Task Ptr, may take a minute')
            self.getCurrentTaskPtr()
        else: 
            self.lgr.warning('Using existing Current Task ptr of 0x%x' % self.param.current_task)
        #idle = self.taskUtils.findSwapper(self.current_task, self.cpu)
        #print('real swapper is 0x%x' % idle)
        self.trecs = []
        SIM_run_command('pselect cpu-name = %s' % self.cpu.name)
        if self.param.current_task_fs:
            cmd = 'logical-to-physical fs:0x%x' % self.param.current_task
        else:
            cmd = 'logical-to-physical 0x%x' % self.param.current_task
        phys = SIM_run_command(cmd)
        self.current_task_phys = phys
        pcell = self.cpu.physical_memory
        self.task_break = SIM_breakpoint(pcell, Sim_Break_Physical, Sim_Access_Write, phys, self.mem_utils.WORD_SIZE, 0)
        self.task_hap = SIM_hap_add_callback_index("Core_Breakpoint_Memop", self.changedThread, self.cpu, self.task_break)
        self.stop_hap = SIM_hap_add_callback("Core_Simulation_Stopped", self.swapperStopHap, None)
        self.lgr.debug('runUntilSwapper set break at 0x%x (phys 0x%x) and callback, now continue' % (self.param.current_task, phys))
        SIM_run_command('c')
     

    def getInit(self):
        ''' Assuming we have swapper in init.idle, find init and use it to locate
            next, prev, pid and comm '''
        #print('real_parent is %d  children %d' % (self.param.ts_real_parent, self.param.ts_children_list_head))
        swapper_child = self.mem_utils.readPtr(self.cpu, self.idle+self.param.ts_children_list_head) 
        self.lgr.debug('getInit swapper_child_next is 0x%x  sib %d' % (swapper_child, self.param.ts_sibling_list_head))
        init = swapper_child - self.param.ts_sibling_list_head
        self.lgr.debug('getInit init is 0x%x' % init)
        next_offset = 20
        #self.lgr.debug('getInit real next is %d' % self.real_param.ts_next)
        for i in range(800):
            swap_next_value = self.mem_utils.readPtr(self.cpu, self.idle + next_offset) 
            swap_next = swap_next_value - next_offset
            self.lgr.debug('getInit look for 0x%x swap_next_value 0x%x swap_next 0x%x' % (init, swap_next_value, swap_next))
            if swap_next == init:
                self.lgr.debug('getInit think next is %d' % next_offset)
                self.param.ts_next = next_offset
                self.param.ts_prev = next_offset + 4
                break
            else:
                next_offset += 4
        if self.param.ts_next is None:
            self.lgr.error('failed to find ts_next')
            return
        ''' loop until we have a child of the init process '''
        
        init_has_child = False
        test_val = 0x5000
        while not init_has_child:   
            init_next_ptr = self.mem_utils.readPtr(self.cpu, init + self.param.ts_next) 
            delta = abs(init - init_next_ptr)
            self.lgr.debug('getInit ts_next %d  ptr 0x%x delta 0x%x' % (self.param.ts_next, init_next_ptr, delta))
            if self.mem_utils.getUnsigned(delta) < test_val:
                self.lgr.debug('got second proc')
                init_has_child = True
            else:
                self.lgr.debug('only one proc, continue')
                SIM_run_command('c 500000') 


        #self.lgr.debug('getInit real pid is %d' % self.real_param.ts_pid)
        init_next_ptr = self.mem_utils.readPtr(self.cpu, init + self.param.ts_next) 
        init_next = init_next_ptr - self.param.ts_next
        self.lgr.debug('getInit ts_next %d  ptr 0x%x init_next is 0x%x' % (self.param.ts_next, init_next_ptr, init_next))
        pid_offset = 0
        init_pid = 0
        next_pid = 0
        for i in range(800):
            init_pid = self.mem_utils.readWord32(self.cpu, init+pid_offset)
            next_pid = self.mem_utils.readWord32(self.cpu, init_next+pid_offset)
            init_pid_g = self.mem_utils.readWord32(self.cpu, init+pid_offset+4)
            next_pid_g = self.mem_utils.readWord32(self.cpu, init_next+pid_offset+4)
            if init_pid == 1 and init_pid_g ==1 and ((next_pid == 2 and next_pid_g == 2) or (next_pid == 0 and next_pid_g == 0)):
                self.lgr.debug('getInit looking for pid, got 1 at offset %d' % pid_offset)
                self.param.ts_pid = pid_offset
                self.param.ts_tgid = pid_offset+4
                break
            else:
                self.lgr.debug('looking for pid offset %d init_pid of %d next_pid %d init_pid_g %d  next_pid_g %d' % (pid_offset, init_pid, next_pid, init_pid_g, next_pid_g))
            pid_offset += 4
         
        if self.param.ts_pid is not None:
            got_comm = False
            self.lgr.debug('getInit look for comm from task 0x%x' % (init))
            while not got_comm:
                comm_offset = self.param.ts_pid+8
                #self.lgr.debug('getInit real comm at %d' % (self.real_param.ts_comm))
                for i in range(800):
                    comm = self.mem_utils.readString(self.cpu, init+comm_offset, 16)
                    if comm.startswith('init') or comm.startswith('systemd'):
                        self.lgr.debug('getInit found comm %s at %d' % (comm, comm_offset))
                        self.param.ts_comm = comm_offset
                        got_comm = True
                        break
                    else:
                        #self.lgr.debug('offset %d comm: %s' % (comm_offset, comm))
                        pass
                    comm_offset += 4
                #self.lgr.debug('getInit out of comm loop')
                if not got_comm:
                    SIM_run_command('c 50000000')
        else:
            self.lgr.error('failed to find ts_pid')
            return
        if self.param.ts_comm is None:
            self.lgr.error('Failed t find comm offset')    
        self.lgr.debug('getInit done')

    def checkTasks(self):        
        #self.lgr.debug(self.param.getParamString())
        self.taskUtils = taskUtils.TaskUtils(self.cpu, self.param, self.mem_utils, self.unistd32, self.lgr)
        swapper_child = self.mem_utils.readPtr(self.cpu, self.idle+self.param.ts_children_list_head) 
        self.lgr.debug('checkTasks swapper_child_next is 0x%x  sib %d' % (swapper_child, self.param.ts_sibling_list_head))
        init = swapper_child - self.param.ts_sibling_list_head
        ts = self.taskUtils.readTaskStruct(init, self.cpu)
        try:
            self.lgr.debug('checkTasks, init pid is %d' % ts.pid)
        except:
            print(dir(ts))
        self.lgr.debug('now get tasks')
        tasks = self.taskUtils.getTaskStructs()
        plist = {}
        for t in tasks:
            plist[tasks[t].pid] = t 
        for pid in sorted(plist):
            t = plist[pid]
            print('pid: %d taks_rec: 0x%x  comm: %s children 0x%x 0x%x' % (tasks[t].pid, t, tasks[t].comm, tasks[t].children[0], tasks[t].children[1]))
        
        
   
    def modeChanged(self, cpu, one, old, new):
        if self.mode_hap is None:
            return
        eip = self.mem_utils.getRegValue(self.cpu, 'eip')
        if old == Sim_CPU_Mode_Supervisor:
            ''' leaving kernel, capture iret and sysexit '''
            if eip not in self.hits:
                self.hits.append(eip)
                instruct = SIM_disassemble_address(self.cpu, eip, 1, 0)
                self.lgr.debug('modeChanged kernel exit eip 0x%x %s' % (eip, instruct[1]))
                if instruct[1] == 'iretd':
                    self.param.iretd = eip
                elif instruct[1] == 'sysexit':
                    self.param.sysexit = eip
                if self.param.iretd is not None and self.param.sysexit is not None:
                    self.lgr.debug('modeChanged found exits')
                    SIM_break_simulation('found sysexit and iretd')
            
        elif old == Sim_CPU_Mode_User:
            self.dumb_count += 1
            instruct = SIM_disassemble_address(self.cpu, eip, 1, 0)
            if self.param.sys_entry is None and instruct[1].startswith('int 128'):
                self.lgr.debug('mode changed old %d  new %d eip: 0x%x %s' % (old, new, eip, instruct[1]))
                self.prev_instruct = instruct[1]
                self.lgr.debug('modeChanged found int 128')
                SIM_break_simulation('found int 128')
            elif self.param.sysenter is None and instruct[1].startswith('sysenter'):
                self.lgr.debug('mode changed old %d  new %d eip: 0x%x %s' % (old, new, eip, instruct[1]))
                self.prev_instruct = instruct[1]
                self.lgr.debug('modeChanged found sysenter')
                SIM_break_simulation('modeChanged found sysenter')
            if self.dumb_count > 1000000:
                self.lgr.debug('modeChanged did 1000')
                SIM_break_simulation('did 10000')
    
    def stepCompute(self, dumb=None): 
        self.lgr.debug('stepCompute')
        SIM_delete_breakpoint(self.task_break)
        SIM_hap_delete_callback_id("Core_Breakpoint_Memop", self.task_hap)
        SIM_hap_delete_callback_id("Core_Simulation_Stopped", self.stop_hap)
        self.task_hap = None
        self.computeStopHap = None
        ''' find where we do the syscall jump table computation '''
        prefix = 'call dword ptr [eax*4'
        prefix1 = 'mov eax,dword ptr [eax*4'
        count = 0
        while True:
            SIM_run_command('si -q')
            eip = self.mem_utils.getRegValue(self.cpu, 'eip')
            instruct = SIM_disassemble_address(self.cpu, eip, 1, 0)
            if instruct[1].startswith(prefix) or instruct[1].startswith(prefix1):
                self.param.syscall_compute = eip
                print(instruct[1])
                self.param.syscall_jump = int(instruct[1].split('-')[1][:-1], 16)
                self.lgr.debug('got compute at 0x%x jump constant is 0x%x  %s' % (eip, self.param.syscall_jump, instruct[1]))
                break
            count += 1
            if count > 1000:
                self.lgr.error('failed to find compute %s' % prefix)
                break

        SIM_run_alone(self.fixStackFrame, None)

    def computeStopHap(self, dumb, one, exception, error_string):
        if self.stop_hap is None:
            return
        self.lgr.debug('computeStopHap')
        SIM_run_alone(self.stepCompute, None)

    def computeDoStop(self, dumb, third, forth, memory):
        self.lgr.debug('computeDoStop must be at sys_entry')
        SIM_break_simulation('computeDoStop')

    def findCompute(self, dumb=None):
        #cell = self.cell_config.cell_context[self.target]
        self.task_break = SIM_breakpoint(self.cell, Sim_Break_Linear, Sim_Access_Execute, self.param.sys_entry, 1, 0)
        self.task_hap = SIM_hap_add_callback_index("Core_Breakpoint_Memop", self.computeDoStop, None, self.task_break)
        self.stop_hap = SIM_hap_add_callback("Core_Simulation_Stopped", self.computeStopHap, None)
        SIM_run_command('c')


    def stopHap(self, dumb, one, exception, error_string):
        if self.stop_hap is None: 
            return
        eip = self.mem_utils.getRegValue(self.cpu, 'eip')
        eax = self.mem_utils.getRegValue(self.cpu, 'eax')
        instruct = SIM_disassemble_address(self.cpu, eip, 1, 0)
        self.lgr.debug('stop hap instruct is %s eip 0x%x  %s' % (instruct[1], eip, instruct[0]))
        do_not_continue = False
        if self.prev_instruct.startswith('int 128') and self.param.sys_entry is None:
            self.lgr.debug('stopHap is int 128')
            self.param.sys_entry = eip 

            ''' NOTE MUST delete these before call to findCompute'''
            #SIM_hap_delete_callback_id("Core_Mode_Change", self.mode_hap)
            #self.mode_hap = None
            #SIM_hap_delete_callback_id("Core_Simulation_Stopped", self.stop_hap)
            #self.stop_hap = None
            #SIM_run_alone(self.findCompute, None)

        elif self.prev_instruct == 'sysenter' and self.param.sysenter is None:
            self.lgr.debug('stopHap is sysenter eax %d' % eax)
            self.param.sysenter = eip 
            #SIM_run_alone(self.findCompute, None)
            
        if self.param.sysenter is not None and self.param.sys_entry is not None \
                 and self.param.sysexit is not None and self.param.iretd is not None:
            SIM_hap_delete_callback_id("Core_Mode_Change", self.mode_hap)
            SIM_hap_delete_callback_id("Core_Simulation_Stopped", self.stop_hap)
            self.stop_hap = None
            self.mode_hap = None

            self.lgr.debug('kernel entry and exits found')

            ''' HERE is where we do more stuff, at the end of this HAP '''
            #param_json = json.dumps(self.param)
            #SIM_run_alone(self.fixStackFrame, None)
            SIM_run_alone(self.findCompute, None)
        elif not do_not_continue:
            self.lgr.debug('now continue')
            SIM_run_alone(SIM_run_command, 'c')


    def checkKernelEntry(self, dumb):
        #SIM_run_command('enable-reverse-execution')
        self.lgr.debug('checkKernelEntry')
        self.dumb_count = 0
        self.hits = []
        self.mode_hap = SIM_hap_add_callback_obj("Core_Mode_Change", self.cpu, 0, self.modeChanged, self.cpu)
        self.stop_hap = SIM_hap_add_callback("Core_Simulation_Stopped", self.stopHap, None)
        self.lgr.debug('checkKernelEntry added mode changed and stop hap, continue')
        SIM_run_command('c')

    def saveParam(self):
        self.lgr.debug('saveParam')
        fname = '%s.param' % self.target
        pickle.dump( self.param, open( fname, "wb" ) )
        self.param.printParams()
        print('Param file stored in %s' % fname)

    def userEIPStopHap(self, dumb, one, exception, error_string):
        SIM_delete_breakpoint(self.task_break)
        SIM_hap_delete_callback_id("Core_Simulation_Stopped", self.stop_hap)
        SIM_hap_delete_callback_id("Core_Breakpoint_Memop", self.task_hap)
        SIM_run_alone(self.setPageFaultHap, None)
        
    def findUserEIP(self, user_eip, third, forth, memory):
        dumb, comm, pid = self.taskUtils.curProc() 
        self.lgr.debug('findUserEIP of 0x%x pid %d wanted %d' % (user_eip, pid, self.current_pid))
        if self.current_pid != pid:
            return
        esp = self.mem_utils.getRegValue(self.cpu, 'esp')
        ''' adjust to start of frame  eh?'''
        #start = esp + self.mem_utils.WORD_SIZE
        start = esp 
        esp = start
        ''' TBD what about 64 bit? '''
        ret_eip = user_eip + 2
        for i in range(800):
            stack_val = self.mem_utils.readPtr(self.cpu, esp)
            if stack_val == ret_eip:
                self.lgr.debug('findUserEIP GOT it at 0x%x' % esp)
                self.param.stack_frame_eip = esp - start
                #SIM_break_simulation('got eip offset')
                break
            esp = esp + self.mem_utils.WORD_SIZE
        if self.param.stack_frame_eip is None:
            self.lgr.error('FAILED to find eip 0x%x' % user_eip)

        self.lgr.debug('findUserEIP break simulation')
        SIM_break_simulation('findUserEIP')
        

    def fixFrameHap(self, user_eip):
        if self.mode_hap is None:
            return
        #cell = self.cell_config.cell_context[self.target]
        self.lgr.debug('fixFramHap, remove mode hap and set break on 0x%x' % self.param.syscall_compute)
        SIM_hap_delete_callback_id("Core_Mode_Change", self.mode_hap)
        self.task_break = SIM_breakpoint(self.cell, Sim_Break_Linear, Sim_Access_Execute, self.param.syscall_compute, 1, 0)
        self.task_hap = SIM_hap_add_callback_index("Core_Breakpoint_Memop", self.findUserEIP, user_eip, self.task_break)
        self.stop_hap = SIM_hap_add_callback("Core_Simulation_Stopped", self.userEIPStopHap, None)
        #SIM_break_simulation('fixframe fix')
         
 
    def fixFrameModeChanged(self, cpu, one, old, new):
        if old == Sim_CPU_Mode_User:
            eip = self.mem_utils.getRegValue(self.cpu, 'eip')
            instruct = SIM_disassemble_address(self.cpu, eip, 1, 0)
            if instruct[1].startswith('int 128'):
                eax = self.mem_utils.getRegValue(self.cpu, 'eax')
                dumb, comm, self.current_pid = self.taskUtils.curProc() 
                self.lgr.debug('fixFrameModeChanged eip is 0x%x pid %d' % (eip, self.current_pid))
                #SIM_break_simulation('here maybe?')
                SIM_run_alone(self.fixFrameHap, eip)

    def fixStackFrame(self, dumb):
        self.lgr.debug('fixStackFrame add modeChanged hap')
        self.mode_hap = SIM_hap_add_callback_obj("Core_Mode_Change", self.cpu, 0, self.fixFrameModeChanged, self.cpu)
        SIM_run_command('c')

    def pageStopHap(self, dumb, one, exception, error_string):
        if self.page_stop_hap is not None:
            SIM_run_alone(self.stepGetEIP, None)
    
    def stepGetEIP(self, dumb):
        if self.param.page_fault is None:
            SIM_run_command('si -q')
            self.param.page_fault = self.mem_utils.getRegValue(self.cpu, 'eip')
            self.lgr.debug('pageStopHap page_fault at 0x%x' % self.param.page_fault)
            SIM_hap_delete_callback_id("Core_Simulation_Stopped", self.page_stop_hap)
            SIM_hap_delete_callback_id("Core_Exception", self.page_hap)
            SIM_break_simulation('stepGetEIP')
            self.page_hap = None
            self.saveParam()

    def pageFaultHap(self, cpu, one, exception_number):
        if self.page_hap is None:
            return
        eip = self.mem_utils.getRegValue(self.cpu, 'eip')
        self.lgr.debug('pageFaultHap eip 0x%x' % eip)
        SIM_break_simulation('pageFaultHap')
        if eip < self.param.kernel_base: 
            SIM_break_simulation('pageFaultHap')
        else:
            self.param.page_fault = eip
            self.lgr.debug('pageFaultHap page_fault right off at 0x%x' % self.param.page_fault)
            SIM_hap_delete_callback_id("Core_Simulation_Stopped", self.page_stop_hap)
            SIM_hap_delete_callback_id("Core_Exception", self.page_hap)
            self.page_hap = None
            self.saveParam()
        

    def setPageFaultHap(self, dumb):
        self.page_hap = SIM_hap_add_callback_obj_index("Core_Exception", self.cpu, 0,
                 self.pageFaultHap, self.cpu, 14)
        self.page_stop_hap = SIM_hap_add_callback("Core_Simulation_Stopped", self.pageStopHap, None)
        self.lgr.debug('setPageFaultHap set exception and stop haps')
        SIM_run_command('c')
        

if __name__ == '__main__':
    gkp = GetKernelParams()
    gkp.runUntilSwapper()
    ''' NOTE: see swapperStopHap hap for follow-on processing and the start of
        as stop hap chain '''
