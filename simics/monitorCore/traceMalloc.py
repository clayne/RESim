from simics import *
class TraceMalloc():
    def __init__(self, top, fun_mgr, context_manager, mem_utils, task_utils, cpu, cell, dataWatch, lgr):
        self.fun_mgr = fun_mgr
        self.cell = cell
        self.cpu = cpu
        self.top = top
        self.context_manager = context_manager
        self.mem_utils = mem_utils
        self.task_utils = task_utils
        self.dataWatch = dataWatch
        self.lgr = lgr
        self.malloc_hap = None
        self.malloc_hap_ret = None
        self.free_hap = None
        self.malloc_list = []
        self.setBreaks()

    class MallocRec():
        def __init__(self, tid, size, cycle):
            self.tid = tid
            self.size = size
            self.addr = None
            self.cycle = cycle

    def stopTrace(self):
        if self.malloc_hap is not None:
            self.context_manager.genDeleteHap(self.malloc_hap)
            self.malloc_hap = None
            self.context_manager.genDeleteHap(self.free_hap)
            self.free_hap = None
        if self.malloc_hap_ret is not None:
            self.context_manager.genDeleteHap(self.malloc_hap_ret)
            self.malloc_hap_ret = None

    def setBreaks(self):
        if self.fun_mgr is not None:
            malloc_fun_addr = self.fun_mgr.getFunEntry('malloc')
            if malloc_fun_addr is not None:
                malloc_break = self.context_manager.genBreakpoint(None, Sim_Break_Linear, Sim_Access_Execute, malloc_fun_addr, 1, 0)
                self.malloc_hap = self.context_manager.genHapIndex("Core_Breakpoint_Memop", self.mallocHap, None, malloc_break, 'malloc')
                free_fun_addr = self.fun_mgr.getFunEntry('free')
                free_break = self.context_manager.genBreakpoint(None, Sim_Break_Linear, Sim_Access_Execute, free_fun_addr, 1, 0)
                self.free_hap = self.context_manager.genHapIndex("Core_Breakpoint_Memop", self.freeHap, None, free_break, 'free')
                #self.lgr.debug('TraceMalloc setBreaks on malloc 0x%x and free 0x%x' % (malloc_fun_addr, free_fun_addr))

            else:
                self.lgr.error('TraceMalloc, address of malloc not found in idaFuns')

    def mallocHap(self, dumb, context, break_num, memory):
        if self.malloc_hap is not None:
            cpu, comm, tid = self.task_utils.curThread() 
            #self.lgr.debug('TraceMalloc mallocHap tid:%s' % tid)
            if cpu.architecture == 'arm':
                size = self.mem_utils.getRegValue(self.cpu, 'r0') 
                #self.lgr.debug('malloc size %d' % size)
                ret_addr = self.mem_utils.getRegValue(self.cpu, 'lr') 
            elif cpu.architecture == 'arm64':
                size = self.mem_utils.getRegValue(self.cpu, 'x0') 
                #self.lgr.debug('malloc size %d' % size)
            else:
                sp = self.mem_utils.getRegValue(self.cpu, 'sp')
                ret_addr = self.mem_utils.readPtr(self.cpu, sp)
                size = self.mem_utils.readWord32(self.cpu, sp+self.mem_utils.WORD_SIZE)
                #self.lgr.debug('TraceMalloc mallocHap malloc size %d ret_addr 0x%x cycle 0x%x' % (size, ret_addr, self.cpu.cycles))
            if not self.top.isLibc(ret_addr, target_cpu=self.cpu) and self.top.getSO(ret_addr, target_cpu=self.cpu) is not None:
                malloc_rec = self.MallocRec(tid, size, cpu.cycles)
                malloc_ret_break = self.context_manager.genBreakpoint(None, Sim_Break_Linear, Sim_Access_Execute, ret_addr, 1, 0)
                self.malloc_hap_ret = self.context_manager.genHapIndex("Core_Breakpoint_Memop", self.mallocEndHap, malloc_rec, malloc_ret_break, 'malloc_end')
            #else:
            #    self.lgr.debug('TraceMalloc mallocHap ret_addr 0x%x is CLIB, skip it cycle 0x%x' % (ret_addr, self.cpu.cycles))

    def freeHap(self, dumb, context, break_num, memory):
        if self.free_hap is not None:
            cpu, comm, tid = self.task_utils.curThread() 
            #self.lgr.debug('TraceMalloc freeHap tid:%s cycle 0x%x' % (tid, self.cpu.cycles))
            if cpu.architecture == 'arm':
                addr = self.mem_utils.getRegValue(self.cpu, 'r0') 
                ret_addr = self.mem_utils.getRegValue(self.cpu, 'lr') 
                #self.lgr.debug('free addr 0x%x' % addr)
            elif cpu.architecture == 'arm64':
                addr = self.mem_utils.getRegValue(self.cpu, 'x0') 
                ret_addr = self.mem_utils.getRegValue(self.cpu, 'lr') 
            else:
                sp = self.mem_utils.getRegValue(self.cpu, 'sp')
                addr = self.mem_utils.readPtr(self.cpu, sp+self.mem_utils.WORD_SIZE)
                ret_addr = self.mem_utils.readPtr(self.cpu, sp)
                #self.lgr.debug('free addr 0x%x' % addr)
            if not self.top.isLibc(ret_addr, target_cpu=self.cpu) and self.top.getSO(ret_addr, target_cpu=self.cpu) is not None:
                self.dataWatch.recordFree(addr)
            #else:
            #    self.lgr.debug('TraceMalloc freeHap ret_addr 0x%x is CLIB, skip it cycle 0x%x' % (ret_addr, self.cpu.cycles))

    def mallocEndHap(self, malloc_rec, context, break_num, memory):
        if self.malloc_hap_ret is not None:
            cpu, comm, tid = self.task_utils.curThread() 
            #self.lgr.debug('TraceMalloc mallocEndHap tid:%s cycle 0x%x' % (tid, self.cpu.cycles))
            if cpu.architecture == 'arm':
                addr = self.mem_utils.getRegValue(self.cpu, 'r0') 
                #self.lgr.debug('malloc addr 0x%x' % addr)
            elif cpu.architecture == 'arm':
                addr = self.mem_utils.getRegValue(self.cpu, 'x0') 
                #self.lgr.debug('malloc addr 0x%x' % addr)
            else:
                addr = self.mem_utils.getRegValue(self.cpu, 'eax') 
                #self.lgr.debug('TraceMalloc mallocEndHap addr 0x%x, size: %d' % (addr, malloc_rec.size))
            malloc_rec.addr = addr
            self.malloc_list.append(malloc_rec)
            self.context_manager.genDeleteHap(self.malloc_hap_ret)
            self.malloc_hap_ret = None
            self.dataWatch.recordMalloc(addr, malloc_rec.size)

    def showList(self):
        for rec in self.malloc_list:
            print('%4d \t0x%x\t%d' % (rec.tid, rec.addr, rec.size))
