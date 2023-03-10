#!/usr/bin/env python
import os
import re
import syscall
from simics import *
'''
Manage one Dmod.  
'''
def nextLine(fh):
   retval = None
   while retval is None:
       line = fh.readline()
       if line is None or len(line) == 0:
           break
       if line.startswith('#'):
           continue
       if len(line.strip()) == 0:
           continue
       retval = line.strip('\n')
   return retval

def getKeyValue(item):
    key = None
    value = None
    if '=' in item:
        parts = item.split('=', 1)
        key = parts[0].strip()
        value = parts[1].strip()
    return key, value

class DmodSeek():
    def __init__(self, delta, pid, fd):
        self.delta = delta
        self.pid = pid
        self.fd = fd

class Dmod():
    class Fiddle():
        def __init__(self, match, was, becomes, cmds=[]):
            self.match = match
            self.was = was
            self.becomes = becomes        
            self.cmds = cmds        


    def __init__(self, top, path, mem_utils, cell_name, lgr, comm=None):
        self.top = top
        self.kind = None
        self.fiddle = None
        self.mem_utils = mem_utils
        self.lgr = lgr
        self.stop_hap = None
        self.cell_name = cell_name
        self.path = path
        self.comm = comm
        self.operation = None
        self.count = 1
        self.fd = None
        self.pid = None
        self.fname_addr = None
        if os.path.isfile(path):
            with open(path) as fh:
               done = False
               kind_line = nextLine(fh) 
               parts = kind_line.split()
               self.kind = parts[0]
               if len(parts) > 1:
                   self.operation = parts[1]
               else:
                   self.lgr.error('Dmod command missing operation %s' % kind_line)
                   return
               start_part = 2
               if len(parts) > start_part:
                   try:
                       self.count = int(parts[start_part])
                       start_part = start_part + 1
                   except:
                       if '=' not in parts[2]:
                           self.lgr.error('Expected count in kind line: %s' % kind_line)
                           return
                   self.lgr.debug('dmod start_part is %d len %d' % (start_part, len(parts)))
                   if len(parts) > start_part:
                       for item in parts[start_part:]:
                           key, value = getKeyValue(item)
                           self.lgr.debug('dmod key <%s> value %s' % (key, value))
                           if key is None:
                               self.lgr.error('Expected key=value in %s' % item)
                               return
                           if key == 'count':
                               self.count = value
                           elif key == 'comm':
                               self.comm = value

               self.lgr.debug('Dmod of kind %s  cell is %s count is %d comm: %s' % (self.kind, self.cell_name, self.count, self.comm))
               if self.kind == 'full_replace':
                   match = nextLine(fh) 
                   becomes=''
                   while not done:
                      line = fh.readline()
                      if line is None or len(line)==0:
                          done = True
                          break
                      if len(becomes)==0:
                          becomes=line
                      else:
                          becomes=becomes+line
                   self.fiddle = self.Fiddle(match, None, becomes)
               elif self.kind == 'match_cmd':
                   match = nextLine(fh) 
                   was = nextLine(fh) 
                   cmds=[] 
                   while not done:
                      line = nextLine(fh)
                      if line is None or len(line)==0:
                          done = True
                          break
                      cmds.append(line)
                   self.fiddle = self.Fiddle(match, was, None, cmds=cmds)
               elif self.kind == 'sub_replace':
                   while not done:
                       match = nextLine(fh) 
                       if match is None:
                           done = True
                           break
                       was = nextLine(fh)
                       becomes = nextLine(fh) 
                       self.fiddle = self.Fiddle(match, was, becomes)
               elif self.kind == 'script_replace':
                   while not done:
                       match = nextLine(fh) 
                       if match is None:
                           done = True
                           break
                       was = nextLine(fh)
                       becomes = nextLine(fh) 
                       self.fiddle = self.Fiddle(match, was, becomes)
               elif self.kind == 'open_replace':
                   match = nextLine(fh) 
                   length = nextLine(fh) 
                   becomes_file = nextLine(fh)
                   if not os.path.isfile(becomes_file):
                       self.lgr.error('Dmod, open_replace expected file name, could not find %s' % becomes_file)
                       return
                   becomes = None
                   with open(becomes_file, 'rb') as bf_fh:
                       becomes = bf_fh.read()
                   # hack using "was" as length
                   self.fiddle = self.Fiddle(match, length, becomes)

               else: 
                   print('Unknown dmod kind: %s' % self.kind)
                   return
            self.lgr.debug('Dmod loaded fiddle of kind %s' % (self.kind))
        else:
            self.lgr.error('Dmod, no file at %s' % path)

    def subReplace(self, cpu, s, addr):
        rm_this = False
        #self.lgr.debug('Dmod checkString  %s to  %s' % (fiddle.match, s))
        try:
            match = re.search(self.fiddle.match, s, re.M|re.I)
        except:
            self.lgr.error('dmod subReplace re.search failed on match: %s, str %s' % (self.fiddle.match, s))
            return False
        if match is not None:
            try:
                was = re.search(self.fiddle.was, s, re.M|re.I)
            except:
                self.lgr.error('dmod subReplace re.search failed on was: %s, str %s' % (self.fiddle.was, s))
                return
            if was is not None:
                self.lgr.debug('Dmod cell: %s replace %s with %s in \n%s' % (self.cell_name, self.fiddle.was, self.fiddle.becomes, s))
                new_string = re.sub(self.fiddle.was, self.fiddle.becomes, s)
                self.top.writeString(addr, new_string, target_cpu=cpu)
            else:
                #self.lgr.debug('Dmod found match %s but not string %s in\n%s' % (fiddle.match, fiddle.was, s))
                pass
                 
            rm_this = True
        return rm_this

    def scriptReplace(self, cpu, s, addr, pid, fd):
        rm_this = False
        checkline = None
        lines = s.splitlines()
        for line in lines:
            #self.lgr.debug('Dmod check line %s' % (line))
            line = line.strip()
  
            if len(line) == 0 or line.startswith('#'):
                continue
            elif line.startswith(self.fiddle.match):
                checkline = line
                break
            else:
                return None
        if checkline is None:
            return False
        #self.lgr.debug('Dmod checkString  %s to line %s' % (self.fiddle.match, checkline))
        try:
            was = re.search(self.fiddle.was, checkline, re.M|re.I)
        except:
            self.lgr.error('dmod subReplace re.search failed on was: %s, str %s' % (self.fiddle.was, checkline))
            return None
        if was is not None:
            self.lgr.debug('Dmod replace %s with %s in \n%s' % (self.fiddle.was, self.fiddle.becomes, checkline))
            new_string = re.sub(self.fiddle.was, self.fiddle.becomes, s)
            #self.lgr.debug('newstring is: %s' % new_string)
            self.top.writeString(addr, new_string, target_cpu=cpu)
            new_line = re.sub(self.fiddle.was, self.fiddle.becomes, checkline)
            if len(checkline) != len(new_line):
                ''' Adjust future _lseek calls, which are caught in syscall.py '''
                delta = len(checkline) - len(new_line)
                diddle_lseek = DmodSeek(delta, pid, fd)
                operation = ['_llseek', 'close']
                call_params = syscall.CallParams(operation, diddle_lseek)        
                cell = self.top.getCell(cell_name=self.cell_name)
                ''' Provide explicit cell to avoid defaulting to the contextManager.  Cell is typically None.'''
                self.top.runTo(operation, call_params, run=False, ignore_running=True, cell_name=self.cell_name, cell=cell)
                self.lgr.debug('Dmod set syscall for lseek diddle delta %d pid:%d fd %d' % (delta, pid, fd))
            else:
                self.lgr.debug('replace caused no change %s\n%s' % (checkline, new_line))
        else:
            #self.lgr.debug('Dmod found match %s but not string %s in\n%s' % (fiddle.match, fiddle.was, s))
            pass
             
        rm_this = True
        return rm_this

    def fullReplace(self, cpu, s, addr):
        rm_this = False
        #self.lgr.debug('dmod fullReplace is %s in %s' % (self.fiddle.match, s))
        if self.fiddle.match in s:
            self.lgr.debug('dmod got match')
            count = len(self.fiddle.becomes)
            self.mem_utils.writeString(cpu, addr, self.fiddle.becomes, target_cpu=cpu)
            if self.operation == 'write':
                esp = self.mem_utils.getRegValue(cpu, 'esp')
                count_addr = esp + 3*self.mem_utils.WORD_SIZE
                self.top.writeWord(count_addr, count)
            else:
                self.top.writeRegValue('syscall_ret', count)
            #cpu.iface.int_register.write(reg_num, count)
            self.lgr.debug('dmod fullReplace %s in %s wrote %d bytes' % (self.fiddle.match, s, count))
            rm_this = True
            #SIM_break_simulation('deeedee')
        return rm_this

    def stopAlone(self, fiddle):
        self.stop_hap = SIM_hap_add_callback("Core_Simulation_Stopped", self.stopHap, fiddle)
        SIM_break_simulation('matchCmd')

    def matchCmd(self, s):
        ''' The match lets us stop looking regardless of whether or not the values are
            bad.  The "was" tells us a bad value, i.e., reason to run commands '''
        rm_this = None
        #self.lgr.debug('look for match of %s in %s' % (fiddle.match, s))
        if re.search(self.fiddle.match, s, re.M|re.I) is not None:
            #self.lgr.debug('found match of %s in %s' % (self.fiddle.match, s))
            rm_this = self.fiddle
            if re.search(self.fiddle.was, s, re.M|re.I) is not None:
                SIM_run_alone(self.stopAlone, self.fiddle)
        return rm_this

    def checkString(self, cpu, addr, count, pid=None, fd=None):
        ''' Modify content at the given addr if content meets the Dmod criteria '''
        retval = False
        byte_array = self.mem_utils.getBytes(cpu, count, addr)
        if byte_array is None:
            self.lgr.debug('Dmod checkstring bytearray None from 0x%x' % addr)
            return retval
        s = ''.join(map(chr,byte_array))
        rm_this = False
        if self.kind == 'sub_replace':
            rm_this = self.subReplace(cpu, s, addr)
        elif self.kind == 'script_replace':
            rm_this = self.scriptReplace(cpu, s, addr, pid, fd)
        elif self.kind == 'full_replace':
            rm_this = self.fullReplace(cpu, s, addr)
        elif self.kind == 'match_cmd':
            rm_this = self.matchCmd(s)
        elif self.kind == 'open_replace':
           pass
        else:
            print('Unknown kind %s' % self.kind)
            return
        if rm_this:
            self.count = self.count - 1
            self.lgr.debug('Dmod checkString found match cell %s path %s count now %d' % (self.cell_name, self.path, self.count))
            retval = True
        return retval

    def stopHap(self, fiddle, one, exception, error_string):
        SIM_hap_delete_callback_id("Core_Simulation_Stopped", self.stop_hap)
        self.lgr.debug('Dmod stop hap')
        for cmd in fiddle.cmds:
            self.lgr.debug('run command %s' % cmd)
            SIM_run_command(cmd)
    
    def getOperation(self):
        return self.operation    
   
    def getPath(self):
        return self.path 

    def getCount(self):
        return self.count

    def getComm(self):
        return self.comm

    def setPid(self, pid):
        self.pid = pid

    def setFD(self, fd):
        self.fd = fd

    def getFD(self):
        return self.fd

    def setFnameAddr(self, addr):
        self.fname_addr = addr
    
    def getMatch(self):                
        if self.fiddle is not None:
            return self.fiddle.match
        else:
            return None

    def getWas(self):                
        if self.fiddle is not None:
            return self.fiddle.was
        else:
            return None

    def getBecomes(self):                
        if self.fiddle is not None:
            return self.fiddle.becomes
        else:
            return None

    def resetOpen(self):
        self.lgr.debug('Dmod resetOpen')
        self.fd = None
        self.pid = None

    def getCellName(self):
        return self.cell_name
        
if __name__ == '__main__':
    print('begin')
    d = Dmod('dog.dmod')
