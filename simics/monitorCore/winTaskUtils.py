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
Windows task information, e.g., task lists.
'''
from simics import *
import os
import pickle
import json
import osUtils
import memUtils
class WinTaskUtils():
    COMM_SIZE = 16
    def __init__(self, cpu, cell_name, param, mem_utils, run_from_snap, lgr):
        self.cpu = cpu
        self.cell_name = cell_name
        self.lgr = lgr
        self.param = param
        self.mem_utils = mem_utils
        self.run_from_snap = run_from_snap
        self.phys_current_task = None
        resim_dir = os.getenv('RESIM_DIR')
        self.call_map = {}
        self.call_num_map = {}
        w7mapfile = os.path.join(resim_dir, 'windows', 'win7.json')
        if os.path.isfile(w7mapfile):
            cm = json.load(open(w7mapfile))     
            for call in cm:
                self.call_map[int(call)] = cm[call] 
                ''' drop Nt prefix'''
                self.call_num_map[cm[call][2:]] = int(call)
        else:
            self.lgr.error('WinTaskUtils cannot open %s' % w7mapfile)
            return

        if run_from_snap is not None:
            phys_current_task_file = os.path.join('./', run_from_snap, cell_name, 'phys_current_task.pickle')
            if os.path.isfile(phys_current_task_file):
                self.phys_current_task = pickle.load( open(phys_current_task_file, 'rb') ) 
            else:
                ''' temporary hack TBD '''
                pfile = os.path.join(self.run_from_snap, 'phys.pickle')
                if os.path.isfile(pfile):
                    self.current_task_phys = pickle.load(open(pfile, 'rb'))
                else:
                    self.lgr.error('winTaskUtils did not find %s' % pfile)
                    return

            exec_addrs_file = os.path.join('./', run_from_snap, cell_name, 'exec_addrs.pickle')
            if os.path.isfile(exec_addrs_file):
                self.exec_addrs = pickle.load( open(exec_addrs_file, 'rb') ) 

    def getPhysCurrentTask(self):
        return self.current_task_phys

    def getCurTaskRec(self):
        retval = None
        cur_thread = SIM_read_phys_memory(self.cpu, self.current_task_phys, self.mem_utils.WORD_SIZE)
        if cur_thread is not None:
            retval = self.mem_utils.readPtr(self.cpu, cur_thread+self.param.proc_ptr)
        return retval

    def getMemUtils(self):
        return self.mem_utils

    def syscallNumber(self, call):
        retval = self.call_num_map[call]
        return retval 

    def syscallName(self, call_num):
        retval = self.call_map[call_num][2:]
        return retval 

    def getSyscallEntry(self, callnum):
        ''' given a call number, compute the address of the kernel code that handles the call
            based on observations made walking the instructions that follow syscall entry.''' 
        # looks like  cs:0xfffff800034f1e1d p:0x0034f1e1d  movsx r11,dword ptr [r10+rax*4]
        #             cs:0xfffff800034f1e24 p:0x0034f1e24  sar r11,4
        #             cs:0xfffff800034f1e28 p:0x0034f1e28  add r10,r11
        #                                          ....    call r10
        # syscall_jump is the r10 value.  TBD, this may change based on different call tables, e.g., 
        # windows has separate gui calls?  
        val = callnum * 4 + self.param.syscall_jump
        val = self.mem_utils.getUnsigned(val)
        self.lgr.debug('getComputed syscall_jump 0x%x  val 0x%x  callnum %d' % (self.param.syscall_jump, val, callnum))
        entry = self.mem_utils.readPtr(self.cpu, val)
        if entry is None:
            self.lgr.error('getComputed entry is None reading from 0x%x' % val)
            return None
        entry = entry & 0xffffffff
        entry_shifted = entry >> 4
        computed = self.param.syscall_jump + entry_shifted
        self.lgr.debug('getComputed call 0x%x val 0x%x entry 0x%x entry_shifted 0x%x computed 0x%x' % (callnum, val, entry, entry_shifted, computed))
        return computed

    def curProc(self):
        pid = None
        comm = None
        cur_proc = self.getCurTaskRec()
        pid_ptr = cur_proc + self.param.ts_pid
        pid = self.mem_utils.readWord(self.cpu, pid_ptr)
        if pid is not None:
            #self.lgr.debug('getCurPid cur_proc, 0x%x pid_offset %d pid_ptr 0x%x pid %d' % (cur_proc, self.param.ts_pid, pid_ptr, pid))
            comm = self.mem_utils.readString(self.cpu, cur_proc+self.param.ts_comm, 16)
        else:
            self.lgr.debug('getCurPid cur_thread is None')
        return self.cpu, comm, pid

    def frameFromRegs(self):
        frame = {}
        if self.cpu.architecture == 'arm':
            for p in memUtils.param_map['arm']:
                frame[p] = self.mem_utils.getRegValue(self.cpu, memUtils.param_map['arm'][p])
            cpl = memUtils.getCPL(self.cpu)
            if cpl == 0:
                frame['sp'] = self.mem_utils.getRegValue(self.cpu, 'sp_usr')
                frame['pc'] = self.mem_utils.getRegValue(self.cpu, 'lr')
                frame['lr'] = self.mem_utils.getRegValue(self.cpu, 'lr_usr')
            else:
                frame['sp'] = self.mem_utils.getRegValue(self.cpu, 'sp')
                frame['pc'] = self.mem_utils.getRegValue(self.cpu, 'pc')
                frame['lr'] = self.mem_utils.getRegValue(self.cpu, 'lr')
        else:
            frame['sp'] = self.mem_utils.getRegValue(self.cpu, 'sp')
            frame['pc'] = self.mem_utils.getRegValue(self.cpu, 'pc')
            if self.mem_utils.WORD_SIZE == 8:
                for p in memUtils.param_map['x86_64']:
                    frame[p] = self.mem_utils.getRegValue(self.cpu, memUtils.win_param_map['x86_64'][p])
            else:
                self.lgr.error('winTaskUtils frameFromRegs bad word size?') 
        return frame

    def frameFromRegsComputed(self):
        frame = self.frameFromRegs()

        gs_base = self.cpu.ia32_gs_base
        ptr2stack = gs_base+0x6008
        stack_val = self.mem_utils.readPtr(self.cpu, ptr2stack)
        user_stack = self.mem_utils.readPtr(self.cpu, stack_val-16)
        frame['sp'] = user_stack
        ''' TBD sometimes stepped on???
            r10 is hid in rcx.  don't ask me...
        '''
        frame['param5'] = self.mem_utils.getRegValue(self.cpu, 'rcx')
        frame['param6'] = user_stack
        frame['param1'] = self.mem_utils.readPtr(self.cpu, stack_val-40)
        #rcx = self.mem_utils.getRegValue(self.cpu, 'rcx')
        #rdx = self.mem_utils.getRegValue(self.cpu, 'rdx')
        #r8 = self.mem_utils.getRegValue(self.cpu, 'r8')
        #r9 = self.mem_utils.getRegValue(self.cpu, 'r9')
        return frame
