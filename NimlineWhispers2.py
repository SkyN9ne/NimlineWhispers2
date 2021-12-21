#!/usr/bin/env python
# coding: utf-8

# Adapted from @Outflank and @_DaWouw 's InlineWhispers project. https://github.com/outflanknl/InlineWhispers
# All credit to them for the syswhispers regexp code

import re, random, string, os, platform
import argparse
from pprint import pprint
from SysWhispers2.syswhispers import SysWhispers 

class NimlineWhispers:

	def __init__(self, debug, randomise, nobanner):
		self.debug = debug
		self.randomise = randomise

		# file containing functions we require
		self.functionsInName = "functions.txt"

		# name for temporary files generated with syswhispers2
		self.basename = "nimlinewhispers"
		self.sw2headers = f"{self.basename}.h"
		self.sw2methods = f"{self.basename}.c"

		# paths to SW2 functions and headers added to our eventual nim file
		self.sw2baseh = os.path.join(".", "SysWhispers2", "data", "base.h")
		self.sw2basec = os.path.join(".", "SysWhispers2", "data", "base.c")

		self.fileInName = f"{self.basename}stubs.asm"
		self.fileOutName = "syscalls.nim"

		self.regexFunctionStart = re.compile(r'([a-z0-9]{1,70})(\s+PROC)', re.IGNORECASE)
		self.regexFunctionEnd = re.compile(r'([a-z0-9]{1,70})(\s+ENDP)', re.IGNORECASE)
		self.regexAsmComment = re.compile(r'([^;\r\n]*)', re.IGNORECASE)
		self.regexHexNotation = re.compile(r'([^;\r\n]*[\s\+\[])([0-9a-f]{1,5})(?:h)([^;\r\n]*)', re.IGNORECASE)

		self.functions = []
		self.filterFunctions = False
		self.functionOutputs = {}
		self.functionArgs = {}
		self.function_map = {}

		# initialise class instance of syswhispers2 so we can generate stubs and fetch seed values later
		self.syswhispers = SysWhispers()

		# why someone wouldn't want to print this masterpiece idk
		if not nobanner: self.printBanner()
		
		self.generateSysWhispersOutput()
		self.generate_function_args_mapping()
		self.produce_randomised_function_names()


	def printBanner(self):
		print(r"""
																			
             %              ..%%%%%#               %/.                  
           /%%%%%,.%%%%%%%%%%%%%%%%%%%%%%%%%%%%.%%%%%%                  
       . #%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%.               
  %%*.%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%% ,%%         
   %%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%.         
    #%%%%%%%%%%%%%%.                         %%%%%%%%%%%%%%%%           
      %%%%%%%(                                     %%%%%%%%%            
    &   %%#                                           .%%  ..           
     &&.                          .                     . #&            
      &&&&.               . %&&&&&&&&.                 &&&&             
       &&&&&&&.. .   . (&&&&&&&&&&&&&&&&&%. .     .&&&&&&&              
       .%&&&&&&&&&&&&&&&&&&&&& ___  &&&&&&&&&&&&&&&&&&&&& 
         #&&&&&&&&&&&&&&&&&&& |__ \  &&&&&&&&&&&&&&&&&&&
           ,&&&&&&&&&&&&&&&&&    ) | &&&&&&&&&&&&&&&&&
               &&&&&&&&&&&&&&   / /  &&&&&&&&&&&&&&
                   &&&&&&&&&&  / /_  &&&&&&&&&&
                          %&& |____| &&.
						NimlineWhispers2
						@ajpc500 2021
		""")

	def generateSysWhispersOutput(self):
		'''
		Grab functions from the functions.txt file and 
		pass them to SysWhispers2 to generate our stubs
		'''
		self.read_required_functions_from_file()
		print("\n[i] Using SysWhispers2 to generate asm stubs...")
		self.syswhispers.generate(self.functions, basename=self.basename)
	
	# taken from https://github.com/FalconForceTeam/SysWhispers2BOF/blob/main/syswhispers2bof.py#L23
	def fix_asm_line(self, line):
		if ';' in line:
			line = line.split(';')[0]
		line = line.rstrip()
		line = re.sub('([0-9A-Fa-f]+)h', '0x\\1', line) # Fix f00h => 0xf00
		return line

	def addSysWhispersFunctionBlock(self):
		'''
		Create an emit block that contains both the headers and functions from Sw2 base code.
		Also manually replace the seed value placeholder
		'''
		out = "{.emit: \"\"\"\n"
		
		h = open(self.sw2baseh, mode='r').read()
		if platform.system() == "Windows": h = h.replace('Windows.h', 'windows.h')	
		h = h.replace('<SEED_VALUE>', f'0x{self.syswhispers.seed:08X}')
		h += "#endif\n"
		out += h

		c = open(self.sw2basec, mode='r').read()
		
		# taken from https://github.com/FalconForceTeam/SysWhispers2BOF
		c = c.replace('#include "<BASENAME>.h"', '') # will generate a single file so no need to include other parts
		c = c.replace('SW2_SYSCALL_LIST SW2_SyscallList;', 'SW2_SYSCALL_LIST SW2_SyscallList = {0,1};') # BOF cannot deal with unitialized global variables
		out += c
		out+= "\n\"\"\".}"
		return out

	def produce_randomised_function_names(self):
		if self.randomise: print("\n[i] Producing randomised function mapping...")
		for function in self.functions:
			rand_val = ''.join(random.choices(string.ascii_letters, k=16))
			self.function_map[function] = rand_val if self.randomise else function
			if self.randomise: print("\t{} -> {}".format(function, rand_val))

	def strip_chars(self, str):
		return str.strip("),;")

	def parse_function_arg(self, arg_list):
		argType = argName = ''
		argTypeIndex = argNameIndex = 0

		arg_list = [self.strip_chars(a) for a in arg_list] # clean unneeded characters

		if len(arg_list) > 0:
			if len(arg_list) == 2:
				# TYPE Name
				argTypeIndex = 0
				argNameIndex = 1
			elif len(arg_list) == 3:
				if arg_list[0].upper() in ['IN','OUT'] and arg_list[2].upper() != 'OPTIONAL':
					# IN TYPE Name
					argTypeIndex = 1
					argNameIndex = 2
				elif arg_list[0].upper() not in ['IN','OUT'] and arg_list[2].upper() == 'OPTIONAL':
					# TYPE Name OPTIONAL
					argTypeIndex = 0
					argNameIndex = 1
				elif arg_list[0].upper() not in ['IN','OUT'] and arg_list[1].upper() == '*':
					# TYPE * Name
					argTypeIndex = 0
					argNameIndex = 1

			elif len(arg_list) == 4:
				if arg_list[0].upper() in ['IN','OUT'] and arg_list[1].upper() in ['IN','OUT']:
					# IN OUT TYPE Name
					argTypeIndex = 2
					argNameIndex = 3
				elif arg_list[0].upper() in ['IN','OUT'] and arg_list[1].upper() not in ['IN','OUT'] and arg_list[2].upper() == '*':
					# OUT TYPE * Name
					argTypeIndex = 1
					argNameIndex = 3
				elif arg_list[0].upper() in ['IN','OUT'] and arg_list[1].upper() not in ['IN','OUT'] and arg_list[2].upper() != '*' and arg_list[3].upper() == 'OPTIONAL':
					# OUT TYPE Name OPTIONAL
					argTypeIndex = 1
					argNameIndex = 2
			elif len(arg_list) == 5:
				if arg_list[0].upper() in ['IN','OUT'] and arg_list[1].upper() in ['IN','OUT'] and arg_list[3] == '*':
					# IN OUT TYPE * Name
					argTypeIndex = 2 
					argNameIndex = 4
				elif arg_list[0].upper() in ['IN','OUT'] and arg_list[1].upper() in ['IN','OUT'] and arg_list[4].upper() == 'OPTIONAL':
					# IN OUT TYPE Name OPTIONAL
					argTypeIndex = 2 
					argNameIndex = 3

			if argNameIndex != argTypeIndex: 
				return arg_list[argNameIndex], arg_list[argTypeIndex]
			else:
				print('[i] No idea what we\'re doing with function arg: {}.'.format(arg_list))				

	def get_function_return_type(self, functionName):
		if functionName in self.functionOutputs:
			return self.functionOutputs[functionName]
		else:
			print('[i] We don\'t know the return type for {}, fix this manually.'.format(functionName))
			return 'UNKNOWN'

	def get_function_arguments(self, functionName):
		if functionName in self.functionOutputs:
			argString = ""
			for arg in self.functionArgs[functionName]:
				if argString:
					argString += ", "
				argString += "{}: {}".format(arg[1], arg[0])
			return argString
		else:
			print('[i] We don\'t know the arguments for {}, fix this manually.'.format(functionName))
			return 'UNKNOWN_ARG: UNKNOWN_TYPE'

	def read_required_functions_from_file(self):
		try:
			with open(self.functionsInName, mode='r') as functionsIn:
				self.functions = ['Nt'+f[2:] if f[:2] == 'Zw' else f for f in [l.strip() for l in functionsIn.readlines()]]
				self.filterFunctions = len(self.functions) and "*" not in self.functions
				print('[i] Function filter file "{}" contains {} functions.'.format(self.functionsInName,len(self.functions)))
		except:
			print('[i] Function filter file "{}" not found. So not filtering functions.'.format(self.functionsInName))

	def generate_function_args_mapping(self):
		try:
			with open(self.sw2headers, mode='r') as structsIn:
				inFunction = False
				currentFunction = ''
				currentFunctionArgs = []
				for f in [l.strip() for l in structsIn.readlines()]:
					if f.startswith("EXTERN_C"):
						functionName = currentFunction = f.split()[2].split("(")[0]
						if functionName in self.functions:			
							inFunction = True
							self.functionOutputs[functionName] = f.split()[1]
							if f.endswith(");"):
								inFunction = False
								self.functionArgs[currentFunction] = []
					elif inFunction:
						arg = f.split()
						if len(arg) > 0:
							argType, argName = self.parse_function_arg(arg)
							currentFunctionArgs.append([argName, argType])
						if arg[-1].endswith(");"):
							inFunction = False
							self.functionArgs[currentFunction] = currentFunctionArgs
							currentFunctionArgs = []					
			print('\n[i] Found return types for {} functions.'.format(len(self.functionOutputs)))
			
			if self.debug:
				pprint(self.functionArgs)
		except:
			print('[i] Functions and Structs file "{}" not found. We need this to get return types and args. Exiting...'.format(self.sw2headers))
			exit()

	def write_inline_assembly_to_file(self):
		filterThisFunction = False
		with open(self.fileInName, mode='r') as fileIn:
			lines = fileIn.readlines()
			lines.pop(0)	#remove .code line
			
			out = '{.passC:"-masm=intel".}\n\n'
			out += self.addSysWhispersFunctionBlock() + "\n\n"

			if self.randomise:
				for function in self.functions:
					out += "# {} -> {}\n".format(function, self.function_map[function])

			inFunction = False
			currentFunction = ""
			for line in lines:
				if inFunction:
					if self.regexFunctionEnd.match(line):
						inFunction = False
						out += '' if filterThisFunction else '    \"\"\"'+'\n'
					elif not filterThisFunction:
						mhex = self.regexHexNotation.match(line)
						if mhex:
							out += mhex[1]+'0x'+mhex[2]+mhex[3]+'\n'
						else:
							# instruction that sets SW2 hash
							if "mov ecx" in re.sub(currentFunction, self.function_map[currentFunction], self.regexAsmComment.match(line)[1]):
								out += self.fix_asm_line(re.sub(currentFunction, self.function_map[currentFunction], self.regexAsmComment.match(line)[1]))+'\n'
							else:
								out += re.sub(currentFunction, self.function_map[currentFunction], self.regexAsmComment.match(line)[1])+'\n'
				else:
					mstart = self.regexFunctionStart.match(line)
					if mstart:
						inFunction = True
						currentFunction = mstart[1]
						filterThisFunction = self.filterFunctions and not(mstart[1] in self.functions)
						out += '' if filterThisFunction else 'proc '+ self.function_map[mstart[1]] + '*(' + self.get_function_arguments(mstart[1]) + ')' +': '+ self.get_function_return_type(mstart[1]) + ' {.asmNoStackFrame.} ='+'\n'
						out += '' if filterThisFunction else '    asm \"\"\"\n'
					elif not filterThisFunction:
						out += '\n'
			
			with open(self.fileOutName, mode='w') as fileOut:
				fileOut.write(out)
				fileOut.close()
				print("\n[+] Success! Outputted to {}".format(self.fileOutName))

if __name__ == "__main__":

	parser = argparse.ArgumentParser(description="Convert SysWhispers output to Nim inline assembly.")
	parser.add_argument('--debug', action='store_true', help="Print mapped functions JSON")
	parser.add_argument('--randomise', action='store_true', help="Randomise the NT function names")
	parser.add_argument('--nobanner', action='store_true', help="Skip banner print out")


	args = parser.parse_args()

	nw = NimlineWhispers(args.debug, args.randomise, args.nobanner)
	nw.write_inline_assembly_to_file()