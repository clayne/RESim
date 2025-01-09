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
from simics import *
import pageUtils
import resimUtils
from resimHaps import *
class PageCallbacks():
    def __init__(self, top, cpu, mem_utils, lgr):
        self.cpu = cpu
        self.lgr = lgr
        self.top = top
        self.mem_utils = mem_utils
        self.callbacks = {}
        self.unmapped_addrs = []
        self.missing_pages = {}
        self.missing_page_bases = {}
        self.missing_tables = {}
        self.missing_haps = {}
        self.mode_hap = None

    def setCallback(self, addr, callback, name=None, use_pid=None):
        if use_pid is None:
            self.lgr.debug('pageCallbacks setCallback for 0x%x' % addr)
        else:
            self.lgr.debug('pageCallbacks setCallback for 0x%x use_pid %s' % (addr, use_pid))
        phys_addr = self.mem_utils.v2p(self.cpu, addr, use_pid=use_pid)
        if phys_addr is None or phys_addr == 0:
            if name is None:
                name = 'NONE'
            if addr not in self.callbacks:
                self.callbacks[addr] = {}
            self.callbacks[addr][name] = callback
            self.setTableHaps(addr,use_pid=use_pid)
        else:
            self.lgr.debug('pageCallbacks setCallback for 0x%x pid %d but addr already mapped, just make the call' % (addr, pid))
            if name is None:
                callback(addr)
            else:
                callback(addr, name)

    def setTableHaps(self, addr, use_pid=None):
        table_base = None
        self.lgr.debug('pageCallbacks setTableHaps for 0x%x' % addr)
        if use_pid is not None:
            if self.top.isWindows():
                table_base = self.mem_utils.getWindowsTableBase(self.cpu, use_pid)
            else: 
                table_base = self.mem_utils.getLinuxTableBase(self.cpu, use_pid)
            if table_base is not None:
                self.lgr.debug('pageCallbacks setTableHaps for pid %s table_base is 0x%x' % (use_pid, table_base))
            else:
                self.lgr.debug('pageCallbacks setTableHaps for pid %s failed to get table_base' % use_pid)
        pt = pageUtils.findPageTable(self.cpu, addr, self.lgr, force_cr3=table_base)
        if pt.page_addr is not None:
            if pt.page_addr not in self.missing_pages:
                self.missing_pages[pt.page_addr] = []
                break_num = SIM_breakpoint(self.cpu.physical_memory, Sim_Break_Physical, Sim_Access_Write, pt.page_addr, 1, 0)
                self.lgr.debug('pageCallbacks setCallback no physical address for 0x%x, set break %d on page_addr 0x%x' % (addr, break_num, pt.page_addr))
                self.missing_haps[break_num] = SIM_hap_add_callback_index("Core_Breakpoint_Memop", self.pageHap, 
                      None, break_num)
            self.missing_pages[pt.page_addr].append(addr)
            self.lgr.debug('pageCallbacks setCallback addr 0x%x added to missing pages for page addr 0x%x' % (addr, pt.page_addr))
        elif pt.page_base_addr is not None:
            if pt.page_base_addr not in self.missing_page_bases:
                self.missing_page_bases[pt.page_base_addr] = []
                break_num = SIM_breakpoint(self.cpu.physical_memory, Sim_Break_Physical, Sim_Access_Write, pt.page_base_addr, 1, 0)
                self.lgr.debug('pageCallbacks no physical address for 0x%x, set break %d on page_base_addr 0x%x' % (addr, break_num, pt.page_base_addr))
                self.missing_haps[break_num] = SIM_hap_add_callback_index("Core_Breakpoint_Memop", self.pageBaseHap, 
                      None, break_num)
            self.missing_page_bases[pt.page_base_addr].append(addr)
            self.lgr.debug('pageCallbacks setCallback addr 0x%x added to missing page bases for page addr 0x%x' % (addr, pt.page_base_addr))
        elif pt.ptable_addr is not None:
            if pt.ptable_addr not in self.missing_tables:
                self.missing_tables[pt.ptable_addr] = []
                break_num = SIM_breakpoint(self.cpu.physical_memory, Sim_Break_Physical, Sim_Access_Write, pt.ptable_addr, 1, 0)
                self.lgr.debug('pageCallbacks setCallback no physical address for 0x%x, set break %d on phys ptable_addr 0x%x' % (addr, break_num, pt.ptable_addr))
                self.missing_haps[break_num] = SIM_hap_add_callback_index("Core_Breakpoint_Memop", self.tableHap, 
                      None, break_num)
            self.missing_tables[pt.ptable_addr].append(addr)
            self.lgr.debug('pageCallbacks setCallback addr 0x%x added to missing tables for table addr 0x%x' % (addr, pt.ptable_addr))

    def delModeAlone(self, hap):
        if hap is not None:
            SIM_hap_delete_callback_id("Core_Mode_Change", hap)

    def modeChanged(self, mem_trans, one, old, new):
        if self.mode_hap is None:
            return
        self.lgr.debug('pageCallbacks modeChanged after table updated, check pages in table')
        self.tableUpdated(mem_trans)
        hap = self.mode_hap
        self.mode_hap = None
        SIM_run_alone(self.delModeAlone, hap)
    
    def tableHap(self, dumb, third, break_num, memory):
        length = memory.size
        op_type = SIM_get_mem_op_type(memory)
        type_name = SIM_get_mem_op_type_name(op_type)
        physical = memory.physical_address
        self.lgr.debug('pageCallbacks tableHap phys 0x%x len %d  type %s' % (physical, length, type_name))
        if break_num in self.missing_haps:
            if op_type is Sim_Trans_Store:
                mem_trans = self.MyMemTrans(memory)
                self.mode_hap = SIM_hap_add_callback_obj("Core_Mode_Change", self.cpu, 0, self.modeChanged, mem_trans)
                self.rmTableHap(break_num)
            else:
                self.lgr.error('tableHap op_type is not store')
        else:
            self.lgr.debug('pageCallbacks tableHap breaknum %d not in missing_haps' % break_num) 

    def tableUpdated(self, mem_trans):
            '''
            Called when a page table is updated.  Find all the page entries within this table and set breaks on each.
            '''
            length = mem_trans.length
            op_type = mem_trans.op_type
            type_name = mem_trans.type_name
            physical = mem_trans.physical
            self.lgr.debug('pageCallbacks tableUpdated phys 0x%x len %d  type %s len of missing_tables[physical] %d' % (physical, length, type_name, len(self.missing_tables[physical])))
            #if length == 4 and self.cpu.architecture == 'arm':
            if op_type is Sim_Trans_Store:
                value = mem_trans.value
                if value == 0:
                    #self.lgr.debug('tableHap value is zero')
                    return
                prev_bp = None
                got_one = False
                redo_addrs = []
                for addr in self.missing_tables[physical]:
                    pt = pageUtils.findPageTable(self.cpu, addr, self.lgr, use_sld=value)
                    if pt.page_addr is None or pt.page_addr == 0:
                        self.lgr.debug('pt still not set for 0x%x, page table addr is 0x%x' % (addr, pt.ptable_addr))
                        redo_addrs.append(addr)
                        continue
                    phys_addr = pt.page_addr | (addr & 0x00000fff)
                    self.lgr.debug('callback here also?')
                    self.doCallback(addr)
                del self.missing_tables[physical]
                for addr in redo_addrs:
                    self.setTableHaps(addr)

    def rmBreakHap(self, hap):
        SIM_hap_delete_callback_id('Core_Breakpoint_Memop', hap)

    def rmTableHap(self, break_num):
        self.lgr.debug('pageCalbacks rmTableHap rmTableHap break_num %d' % break_num)
        SIM_delete_breakpoint(break_num)
        hap = self.missing_haps[break_num]
        del self.missing_haps[break_num]
        SIM_run_alone(self.rmBreakHap, hap)

    def pageBaseHap(self, dumb, third, break_num, memory):
        ''' hit when a page base address is updated'''
        if break_num not in self.missing_haps:
            return
        if self.mode_hap is not None:
            #self.lgr.debug('pageCallbacks pageBaseHap already has a mode_hap, bail')
            return
        length = memory.size
        op_type = SIM_get_mem_op_type(memory)
        type_name = SIM_get_mem_op_type_name(op_type)
        physical = memory.physical_address
        cpu, comm, tid = self.top.curThread(target_cpu=self.cpu)
        self.lgr.debug('pageCalbacks pageBaseHap phys 0x%x len %d  type %s tid:%s (%s) cycle: 0x%x' % (physical, length, type_name, tid, comm, cpu.cycles))
        if op_type is Sim_Trans_Store:
            ''' Remove the hap and break.  They will be recreated at the end of this call chain unless all assocaited addresses are mapped. '''
            self.rmTableHap(break_num)
            ''' Set a mode hap so we recheck page entries after kernel finishes its mappings. '''
            mem_trans = self.MyMemTrans(memory)
            self.mode_hap = SIM_hap_add_callback_obj("Core_Mode_Change", self.cpu, 0, self.modeChangedPageBase, mem_trans)
        else:
            self.lgr.error('pageCallbacks pageBaseHap op_type is not store')

    def modeChangedPageBase(self, mem_trans, one, old, new):
        ''' In user mode after seeing that kernel was updating page base '''
        if self.mode_hap is None:
            return
        self.lgr.debug('pageCallbacks modeChanged after page base updated, check pages in page base')
        self.pageBaseUpdated(mem_trans)
        hap = self.mode_hap
        self.mode_hap = None
        SIM_run_alone(self.delModeAlone, hap)
    
    def pageBaseUpdated(self, mem_trans):
            '''
            Called when a page base is updated.  We've returned to the user since the hap was hit.
            The hap was already removed.  Remove all assocaited entries and recreate those that need it.
            '''
            length = mem_trans.length
            op_type = mem_trans.op_type
            type_name = mem_trans.type_name
            physical = mem_trans.physical
            self.lgr.debug('pageBaseUpdated phys 0x%x len %d  type %s len of missing_tables[physical] %d' % (physical, length, type_name, len(self.missing_page_bases[physical])))
            #if length == 4 and self.cpu.architecture == 'arm':
            if op_type is Sim_Trans_Store:
                value = mem_trans.value
                if value == 0:
                    #self.lgr.debug('tableHap value is zero')
                    return
                redo_addrs = []
                for addr in self.missing_page_bases[physical]:
                    pt = pageUtils.findPageTable(self.cpu, addr, self.lgr, use_sld=value)
                    if pt.page_addr is None or pt.page_addr == 0:
                        self.lgr.debug('pageCallbacks pageBaseUpdated pt still not set for 0x%x, page table addr is 0x%x' % (addr, pt.ptable_addr))
                        redo_addrs.append(addr)
                        continue
                    phys_addr = pt.page_addr | (addr & 0x00000fff)
                    #print('would do callback here')
                    self.doCallback(addr)

                del self.missing_page_bases[physical]
                for addr in redo_addrs:
                    self.setTableHaps(addr)

    def doCallback(self, addr):
            self.lgr.debug('pageCallbacks doCallback would do callback here')
            if addr in self.callbacks:
                for name in self.callbacks[addr]:
                    if name == 'NONE':
                        self.lgr.debug('pageCallbacks pageBaseUpdated addr 0x%x callback %s' % (addr, self.callbacks[addr]))
                        self.callbacks[addr]['NONE'](addr)
                    else:
                        self.lgr.debug('pageCallbacks pageBaseUpdated addr 0x%x name %s callback %s' % (addr, name, self.callbacks[addr]))
                        self.callbacks[addr][name](addr, name)
                #SIM_break_simulation('remove this')
            else:
                self.lgr.debug('pageCallbacks pageBaseUpdated addr 0x%x not in callbacks' % (addr))
   
    def pageHap(self, dumb, third, break_num, memory):
        ''' called when a page table entry is updated (mapped). '''
        if break_num in self.missing_haps:
            length = memory.size
            op_type = SIM_get_mem_op_type(memory)
            type_name = SIM_get_mem_op_type_name(op_type)
            physical = memory.physical_address
            if physical not in self.missing_pages:
                self.lgr.error('pageCallback pageHap mem ref physical 0x%x not in missing pages' % physical)
                return

            #self.lgr.debug('pageHap phys 0x%x len %d  type %s' % (physical, length, type_name))
            if op_type is Sim_Trans_Store:
                value = SIM_get_mem_op_value_le(memory)
                #self.lgr.debug('pageHap value is 0x%x' % value)
            for addr in self.missing_pages[memory.physical_address]:
                # TBD this was broken.  Not sure if it is now fixed
                #offset = memUtils.bitRange(pdir_entry, 0, 19)
                #addr = value + offset
                pt = pageUtils.findPageTable(self.cpu, addr, self.lgr)
                phys_addr = pt.page_addr
                if phys_addr is None:
                    self.lgr.error('pageCallbacks pageHap got none for addr ofr addr 0x%x.  broken' % addr) 
                    return
                else:
                    print('callback here also?')
                    self.doCallback(addr)
                    pass
            self.rmTableHap(break_num)
            del self.missing_pages[memory.physical_address]
 
        else:
            self.lgr.debug('pageCallbacks pageHap breaknum should have no hap %d' % break_num)



    class MyMemTrans():
        def __init__(self, memory):
            self.length = memory.size
            self.op_type = SIM_get_mem_op_type(memory)
            self.type_name = SIM_get_mem_op_type_name(self.op_type)
            self.physical = memory.physical_address
            if self.op_type is Sim_Trans_Store:
                self.value = SIM_get_mem_op_value_le(memory)
            else:
                self.value = None
