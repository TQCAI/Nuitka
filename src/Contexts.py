#
#     Copyright 2010, Kay Hayen, mailto:kayhayen@gmx.de
#
#     Part of "Nuitka", an attempt of building an optimizing Python compiler
#     that is compatible and integrates with CPython, but also works on its
#     own.
#
#     If you submit Kay Hayen patches to this software in either form, you
#     automatically grant him a copyright assignment to the code, or in the
#     alternative a BSD license to the code, should your jurisdiction prevent
#     this. Obviously it won't affect code that comes to him indirectly or
#     code you don't submit to him.
#
#     This is to reserve my ability to re-license the code at any time, e.g.
#     the PSF. With this version of Nuitka, using it for Closed Source will
#     not be allowed.
#
#     This program is free software: you can redistribute it and/or modify
#     it under the terms of the GNU General Public License as published by
#     the Free Software Foundation, version 3 of the License.
#
#     This program is distributed in the hope that it will be useful,
#     but WITHOUT ANY WARRANTY; without even the implied warranty of
#     MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#     GNU General Public License for more details.
#
#     You should have received a copy of the GNU General Public License
#     along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
#     Please leave the whole of this copyright notice intact.
#
from Identifiers import namifyConstant, ExceptionCannotNamify, digest, Identifier, LocalVariableIdentifier, ClosureVariableIdentifier

import CodeTemplates

import cPickle, re, hashlib

class PythonContextBase:
    def __init__( self ):
        self.variables = set()

        self.while_loop_count = 0
        self.for_loop_count = 0

        self.try_count = 0
        self.with_count = 0

        self.temp_counter = 0

    def allocateForLoopNumber( self ):
        self.for_loop_count += 1

        return self.for_loop_count

    def allocateWhileLoopNumber( self ):
        self.while_loop_count += 1

        return self.while_loop_count

    def allocateTryNumber( self ):
        self.try_count += 1

        return self.try_count

    def allocateWithNumber( self ):
        self.with_count += 1

        return self.with_count

    def addVariable( self, var_name ):
        self.variables.add( var_name )

    def isClosureViaContext( self ):
        return True

    def isParametersViaContext( self ):
        return False

    def getTempObjectVariable( self ):
        # TODO: Make sure these are actually indepedent in generated code between different
        # contexts

        result = Identifier( "_expression_temps[%d] " % self.temp_counter, 0 )

        self.temp_counter += 1

        return result


class PythonChildContextBase( PythonContextBase ):
    def __init__( self, parent ):
        PythonContextBase.__init__( self )

        self.parent = parent

    def getParent( self ):
        return self.parent

    def getConstantHandle( self, constant ):
        return self.parent.getConstantHandle( constant )

    def addContractionCodes( self, contraction, contraction_identifier, contraction_context, contraction_code, loop_var_codes, contraction_conditions, contraction_iterateds ):
        return self.parent.addContractionCodes( contraction, contraction_identifier, contraction_context, contraction_code, loop_var_codes, contraction_conditions, contraction_iterateds )

    def addLambdaCodes( self, lambda_def, lambda_code, lambda_context ):
        self.parent.addLambdaCodes( lambda_def, lambda_code, lambda_context )

    def addGlobalVariableNameUsage( self, var_name ):
        self.parent.addGlobalVariableNameUsage( var_name )

    def getModuleCodeName( self ):
        return self.parent.getModuleCodeName()

    def getModuleName( self ):
        return self.parent.getModuleName()


class PythonGlobalContext:
    def __init__( self ):
        self.constants = {}
        self.constant_dicts = {}

        self.const_tuple_empty  = self.getConstantHandle( () ).getCode()
        self.const_string_empty = self.getConstantHandle( "" ).getCode()
        self.const_bool_true    = self.getConstantHandle( True ).getCode()
        self.const_bool_false   = self.getConstantHandle( False ).getCode()

        self.module_name__      = self.getConstantHandle( "__module__" ).getCode()
        self.doc__              = self.getConstantHandle( "__doc__" ).getCode()
        self.file__             = self.getConstantHandle( "__file__" ).getCode()

    def getConstantHandle( self, constant ):
        if constant is None:
            return Identifier( "Py_None", 0 )
        elif type( constant ) == dict:
            dict_key = repr( sorted( constant.iteritems() ) )

            if dict_key not in self.constant_dicts:
                self.constant_dicts[ dict_key ] = self._getConstantHandle( constant )

            return Identifier( self.constant_dicts[ dict_key ], 0 )
        elif constant is Ellipsis:
            return Identifier( "Py_Ellipsis", 0 )
        else:
            key = ( type( constant ), repr( constant ), constant )

            if key not in self.constants:
                self.constants[ key ] = self._getConstantHandle( constant )

            return Identifier( self.constants[ key ], 0 )

    def _getConstantHandle( self, constant ):
        if type( constant ) in ( int, long, str, unicode, float, bool, complex ):
            return "_python_" + namifyConstant( constant )
        elif constant == ():
            return "_python_tuple_empty"
        elif type ( constant ) == tuple:
            result = "_python_tuple_"

            try:
                parts = []

                for value in constant:
                    parts.append( namifyConstant( value ) )

                return result + "_".join( parts )
            except ExceptionCannotNamify:
                print "Warning, couldn't namify", value

                return result + digest( repr( constant ) )
        elif type( constant ) == dict:
            if constant == {}:
                return "_python_dict_empty"
            else:
                return "_python_dict_" + hashlib.md5( repr( constant ) ).hexdigest()
        elif constant is Ellipsis:
            return "Py_Ellipsis"
        else:
            raise Exception( "Unknown type for constant handle", type( constant ), constant  )

    def getPreludeCode( self ):
        return CodeTemplates.global_prelude

    def getHelperCode( self ):
        result = CodeTemplates.global_helper
        result += CodeTemplates.import_helper

        result += CodeTemplates.compiled_function_type_code
        result += CodeTemplates.compiled_generator_type_code
        result += CodeTemplates.compiled_genexpr_type_code

        return result

    def getConstantCode( self ):
        return CodeTemplates.constant_reading % {
            "const_init"         : self.getConstantInitializations(),
            "const_declarations" : self.getConstantDeclarations(),
        }

    def getConstantDeclarations( self ):
        statements = []

        for constant_name in sorted( self.constants.values()  ):
            statements.append( "static PyObject *%s = NULL;" % constant_name )

        for constant_name in sorted( self.constant_dicts.values() ):
            statements.append( "static PyObject *%s = NULL;" % constant_name )

        return "\n".join( statements )

    def _pickRawDelimiter( self, value ):
        delimiter = "raw"

        while value.find( delimiter ) != -1:
            delimiter = "_" + delimiter + "_"

        return delimiter

    def _encodeString( self, value ):
        delimiter = self._pickRawDelimiter( value )

        start = 'R"' + delimiter + "("
        end = ")" + delimiter + '"'

        result = start + value + end

        # Replace \n, \r and \0 in the raw strings. The \0 gives a silly warning from
        # gcc (bug reported) and \n and \r even lead to wrong strings. Somehow the
        # parser of the C++ doesn't yet play nice with these.

        def decide( match ):
            if match.group(0) == "\n":
                return end + r' "\n" ' + start
            elif match.group(0) == "\r":
                return end + r' "\r" ' + start
            else:
                return end + r' "\0" ' + start

        result = re.sub( "\n|\r|" + chr(0), decide, result )

        return result

    def getConstantInitializations( self ):
        statements = []

        def myCompare( a, b ):
            if False:
                type_cmp_result = cmp( a[0][0], b[0][0] )

                if type_cmp_result != 0:
                    return type_cmp_result

            return cmp( a[1], b[1] )

        for constant_desc, constant_identifier in sorted( self.constants.iteritems(), cmp = myCompare ):
            constant_type, _constant_repr, constant_value = constant_desc

            if constant_type == int and abs(constant_value) < 2**31:
                # Will fallback to cPickle if they are bigger than PyInt allows.
                statements.append( "%s = PyInt_FromLong( %s );" % ( constant_identifier, constant_value ) )
            elif constant_type == str:
                encoded = self._encodeString( constant_value )

                # statements.append( """puts( "%s" );""" % constant_identifier )
                statements.append( """%s = PyString_FromStringAndSize( %s, %d );""" % ( constant_identifier, encoded, len(constant_value) ) )
                statements.append( """assert( PyString_Size( %s ) == %d );""" % ( constant_identifier, len(constant_value) ) )
            elif constant_type in ( tuple, list, bool, float, complex, unicode, int, long ):
                saved = cPickle.dumps( constant_value )

                # Check that the constant is restored correctly.
                restored = cPickle.loads( saved )

                assert restored == constant_value and repr( constant_value ) == repr( restored ), ( repr( constant_value ), "!=", repr( restored ) )
                # statements.append( """puts( "%s" );""" % constant_identifier )

                statements.append( """%s = _unstreamConstant( %s, %d );""" % ( constant_identifier, self._encodeString( saved ), len( saved ) ) )
            elif constant_value is None:
                pass
            else:
                assert False, (type(constant_value), constant_value, constant_identifier)

        for constant_value, constant_identifier in sorted( self.constant_dicts.iteritems() ):
            dict_value = {}

            for key, value in eval( constant_value ):
                dict_value[ key ] = value

            saved = cPickle.dumps( dict_value )

            # Check that the constant is restored correctly.
            restored = cPickle.loads( saved )
            assert restored == dict_value, dict_value

            # statements.append( """puts( "%s" );""" % constant_identifier )
            statements.append( """%s = _unstreamConstant( %s, %d );""" % ( constant_identifier, self._encodeString( saved ), len( saved ) ) )

        return "\n    ".join( statements )


class PythonModuleContext( PythonContextBase ):
    def __init__( self, module_name, code_name, global_context ):
        PythonContextBase.__init__( self )

        self.name = module_name
        self.code_name = code_name

        self.global_context = global_context
        self.functions = {}

        self.class_codes = {}
        self.function_codes = []
        self.lambda_codes = []
        self.contraction_codes = []

        self.lambda_count = 0

        self.global_var_names = set()

    def getConstantHandle( self, constant ):
        return self.global_context.getConstantHandle( constant )

    def addFunctionCodes( self, function, function_context, function_codes ):
        self.function_codes.append( ( function, function_context, function_codes ) )

    def addClassCodes( self, class_def, class_codes ):
        assert class_def not in self.class_codes

        self.class_codes[ class_def ] = class_codes

    def addLambdaCodes( self, lambda_def, lambda_code, lambda_context ):
        self.lambda_codes.append( ( lambda_def, lambda_code, lambda_context ) )

    def addContractionCodes( self, contraction, contraction_identifier, contraction_context, contraction_code, loop_var_codes, contraction_conditions, contraction_iterateds ):
        self.contraction_codes.append( ( contraction, contraction_identifier, contraction_context, loop_var_codes, contraction_code, contraction_conditions, contraction_iterateds ) )

    def getContractionsCodes( self ):
        return self.contraction_codes

    def getFunctionsCodes( self ):
        return self.function_codes

    def getClassesCodes( self ):
        return self.class_codes

    def getLambdasCodes( self ):
        return self.lambda_codes

    def getGeneratorExpressionCodeHandle( self, generator_def ):
        generator_name = generator_def.getFullName()

        return "_python_generatorfunction_" + generator_name

    def allocateLambdaIdentifier( self ):
        self.lambda_count += 1

        return "_python_modulelambda_%d_%s" % ( self.lambda_count, self.getName() )

    def getName( self ):
        return self.name

    getModuleName = getName

    def getModuleCodeName( self ):
        return self.getCodeName()

    def hasLocalVariable( self, var_name ):
        return False

    def hasClosureVariable( self, var_name ):
        return False

    def canHaveLocalVariables( self ):
        return False

    def addGlobalVariableNameUsage( self, var_name ):
        self.global_var_names.add( var_name )

    def getGlobalVariableNames( self ):
        return self.global_var_names

    def getCodeName( self ):
        return self.code_name

class PythonFunctionContext( PythonChildContextBase ):
    def __init__( self, parent, function, locals_dict ):
        PythonChildContextBase.__init__( self, parent = parent )

        self.function = function
        self.locals_dict = locals_dict

        self.lambda_count = 0

        # Make sure the local names are available as constants
        for local_name in function.getLocalVariableNames():
            self.getConstantHandle( constant = local_name )

    def __repr__( self ):
        return "<PythonFunctionContext for function '%s'>" % self.function.getName()

    def hasLocalVariable( self, var_name ):
        return var_name in self.function.getLocalVariableNames()

    def hasClosureVariable( self, var_name ):
        return var_name in self.function.getClosureVariableNames()

    def canHaveLocalVariables( self ):
        return True

    def isParametersViaContext( self ):
        return self.function.isGenerator()

    def getLocalHandle( self, var_name ):
        return LocalVariableIdentifier( var_name, from_context = self.function.isGenerator() )

    def getClosureHandle( self, var_name ):
        if not self.function.isGenerator():
            return ClosureVariableIdentifier( var_name, from_context = "_python_context->" )
        else:
            return ClosureVariableIdentifier( var_name, from_context = "_python_context->common_context->" )

    def getDefaultHandle( self, var_name ):
        if not self.function.isGenerator():
            return Identifier( "_python_context->default_value_" + var_name, 0 )
        else:
            return Identifier( "_python_context->common_context->default_value_" + var_name, 0 )

    def getLambdaExpressionCodeHandle( self, lambda_expression ):
        return self.parent.getLambdaExpressionCodeHandle( lambda_expression = lambda_expression )

    def getGeneratorExpressionCodeHandle( self, generator_def ):
        return self.parent.getGeneratorExpressionCodeHandle( generator_def = generator_def )

    def allocateLambdaIdentifier( self ):
        self.lambda_count += 1

        return "_python_lambda_%d_%s" % ( self.lambda_count, self.function.getFullName() )

    def addFunctionCodes( self, function, function_context, function_codes ):
        self.parent.addFunctionCodes( function, function_context, function_codes )

    def addClassCodes( self, class_def, class_codes ):
        self.parent.addClassCodes( class_def, class_codes )

    def getCodeName( self ):
        return self.function.getCodeName()


class PythonContractionBase( PythonChildContextBase ):
    def __init__( self, parent, loop_variables, leak_loop_vars ):
        PythonChildContextBase.__init__( self, parent = parent )

        self.loop_variables = tuple( loop_variables )
        self.leak_loop_vars = leak_loop_vars

    def isClosureViaContext( self ):
        return False

    def isListContraction( self ):
        return self.__class__ == PythonListContractionContext

class PythonListContractionContext( PythonContractionBase ):
    def __init__( self, parent, loop_variables ):
        PythonContractionBase.__init__(
            self,
            parent         = parent,
            loop_variables = loop_variables,
            leak_loop_vars = True
        )

    def getClosureHandle( self, var_name ):
        return ClosureVariableIdentifier( var_name, from_context = "" )

    def getLocalHandle( self, var_name ):
        return self.getClosureHandle( var_name )


class PythonGeneratorExpressionContext( PythonContractionBase ):
    def __init__( self, parent, loop_variables ):
        PythonContractionBase.__init__(
            self,
            parent         = parent,
            loop_variables = loop_variables,
            leak_loop_vars = False
        )

    def getClosureHandle( self, var_name ):
        return ClosureVariableIdentifier( var_name, from_context = "_python_context->" )

    def getLocalHandle( self, var_name ):
        return LocalVariableIdentifier( var_name, from_context = True )

class PythonLambdaExpressionContext( PythonChildContextBase ):
    def __init__( self, parent, parameter_names ):
        PythonChildContextBase.__init__( self, parent = parent )

        self.parameter_names = parameter_names

        # Make sure the parameter names are available as constants
        for parameter_name in parameter_names:
            self.getConstantHandle( constant = parameter_name )

    def getClosureHandle( self, var_name ):
        return ClosureVariableIdentifier( var_name, from_context = "_python_context->" )

    def hasLocalVariable( self, var_name ):
        return var_name in self.parameter_names

    def getLocalHandle( self, var_name ):
        return LocalVariableIdentifier( var_name )

    def getDefaultHandle( self, var_name ):
        return Identifier( "_python_context->default_value_" + var_name, 0 )

class PythonClassContext( PythonChildContextBase ):
    def __init__( self, parent, class_def ):
        PythonChildContextBase.__init__( self, parent = parent )

        self.class_def = class_def

    def hasLocalVariable( self, var_name ):
        return var_name in self.class_def.getClassVariableNames()

    def hasClosureVariable( self, var_name ):
        return var_name in self.class_def.getClosureVariableNames()

    def getLocalHandle( self, var_name ):
        return LocalVariableIdentifier( var_name )

    def getClosureHandle( self, var_name ):
        return ClosureVariableIdentifier( var_name, from_context = "" )

    def addFunctionCodes( self, function, function_context, function_codes ):
        self.parent.addFunctionCodes( function, function_context, function_codes )

    def addClassCodes( self, class_def, class_codes ):
        self.parent.addClassCodes( class_def, class_codes )

    def isClosureViaContext( self ):
        return False
