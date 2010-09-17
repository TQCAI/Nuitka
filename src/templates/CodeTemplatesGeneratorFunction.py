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
genfunc_context_body_template = """

// This structure is for attachment as self of the generator function %(function_identifier)s and
// contains the common closure. It is allocated at the time the genexpr object is created.
struct _context_common_%(function_identifier)s_t
{
    // The generator function can access a read-only closure of the creator.
    %(function_common_context_decl)s
};

struct _context_generator_%(function_identifier)s_t
{
    _context_common_%(function_identifier)s_t *common_context;

    // The generator function instance can access its parameters from creation time.
    %(function_instance_context_decl)s
};

static void _context_common_%(function_identifier)s_destructor( void *context_voidptr )
{
    _context_common_%(function_identifier)s_t *_python_context = (struct _context_common_%(function_identifier)s_t *)context_voidptr;

    %(function_context_free)s

    delete _python_context;
}

static void _context_generator_%(function_identifier)s_destructor( void *context_voidptr )
{
    _context_generator_%(function_identifier)s_t *_python_context = (struct _context_generator_%(function_identifier)s_t *)context_voidptr;

    delete _python_context;
}
"""

make_genfunc_with_context_template = """
static PyObject *MAKE_FUNCTION_%(function_identifier)s( %(function_creation_args)s )
{
    struct _context_common_%(function_identifier)s_t *_python_context = new _context_common_%(function_identifier)s_t;

    // Copy the parameter default values and closure values over.
    %(function_context_copy)s

    PyObject *result = Nuitka_Function_New( %(function_identifier)s, %(function_name_obj)s, %(module)s, %(function_doc)s, _python_context, _context_common_%(function_identifier)s_destructor );

    // Apply decorators if any
    %(function_decorator_calls)s

    return result;
}

"""

genfunc_yielder_template = """

static PyTracebackObject *%(function_tb_maker)s( int line )
{
   PyFrameObject *frame = MAKE_FRAME( %(module)s, %(file_identifier)s, %(name_identifier)s, line );

   PyTracebackObject *result = MAKE_TRACEBACK_START( frame, line );

   Py_DECREF( frame );

   assert( result );

   return result;
}

static PyTracebackObject *%(function_tb_adder)s( int line )
{
    PyFrameObject *frame = MAKE_FRAME( %(module)s, %(file_identifier)s, %(name_identifier)s, line );

    // Inlining PyTraceBack_Here may be faster
    PyTraceBack_Here( frame );

    Py_DECREF( frame );
}

static void %(function_identifier)s_context( Nuitka_GeneratorObject *generator )
{
    bool traceback;

    try
    {
        traceback = true;
        CHECK_EXCEPTION( generator );
        traceback = false;

        struct _context_generator_%(function_identifier)s_t *_python_context = (_context_generator_%(function_identifier)s_t *)generator->m_context;

        // Set the names of local variables if any
        %(local_var_naming)s

        // Actual function code.
        %(function_body)s

        PyErr_SetNone( PyExc_StopIteration );
        generator->m_yielded = NULL;
    }
    catch ( _PythonException &_exception )
    {
        _exception.toPython();

        if ( traceback == false )
        {
           ADD_TRACEBACK( %(module)s, %(file_identifier)s, %(name_identifier)s, _exception.getLine() );
        }

        generator->m_yielded = NULL;
    }

    swapcontext( &generator->m_yielder_context, &generator->m_caller_context );
}

"""

genfunc_yield_terminator = """\
    PyErr_SetNone( PyExc_StopIteration );
    throw _PythonException();
"""

genfunc_function_template = """
static PyObject *%(function_identifier)s( PyObject *self, PyObject *args, PyObject *kw )
{
    struct _context_common_%(function_identifier)s_t *_python_common_context = (struct _context_common_%(function_identifier)s_t *)self;

    try
    {
        struct _context_generator_%(function_identifier)s_t *_python_context = new _context_generator_%(function_identifier)s_t;

        %(parameter_parsing_code)s

        _python_context->common_context = _python_common_context;

        PyObject *result = Nuitka_Generator_New( %(function_identifier)s_context, %(function_name_obj)s, _python_context, _context_generator_%(function_identifier)s_destructor );


        if ( result == NULL )
        {
            PyErr_Format( PyExc_RuntimeError, "cannot create function %(function_name)s" );
            throw _PythonException();
        }

        return result;
    }
    catch ( _PythonException &_exception )
    {
        _exception.toPython();

        return NULL;
    }
}
"""
