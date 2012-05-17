#
# QAPI visitor generator
#
# Copyright IBM, Corp. 2011
#
# Authors:
#  Anthony Liguori <aliguori@us.ibm.com>
#  Michael Roth    <mdroth@linux.vnet.ibm.com>
#
# This work is licensed under the terms of the GNU GPLv2.
# See the COPYING.LIB file in the top-level directory.

from ordereddict import OrderedDict
from qapi import *
import sys
import os
import getopt
import errno
import types

def generate_visit_array_body(name, info):
    ret = mcgen('''
visit_start_array(m, (void **)obj, "%(name)s", %(count)s, sizeof(%(type)s), errp);
int %(name)s_i;
for (%(name)s_i = 0; %(name)s_i < %(count)s; %(name)s_i++) {
    visit_type_%(type_short)s(m, &(*obj)->%(name)s[%(name)s_i], NULL, errp);
    visit_next_array(m, errp);
}
visit_end_array(m, errp);
''',
                name=name, type=c_type(info['type'][0]),
                type_short=info['type'][0],
                count=info['array_size'])
    return ret

def generate_visit_array_body(name, info):
    if info.has_key('array_capacity'):
        array_capacity = info['array_capacity']
    else:
        array_capacity = info['array_size']

    if info['array_size'].isdigit():
        array_size = info['array_size']
    else:
        array_size = "(*obj)->%s" % info['array_size']

    ret = mcgen('''
visit_start_array(m, (void **)obj, "%(name)s", %(array_capacity)s, sizeof(%(type)s), errp);
int %(name)s_i;
for (%(name)s_i = 0; %(name)s_i < %(array_size)s; %(name)s_i++) {
    visit_type_%(type_short)s(m, &(*obj)->%(name)s[%(name)s_i], NULL, errp);
    visit_next_array(m, errp);
}
visit_end_array(m, errp);
''',
                name=name, type=c_type(info['type'][0]),
                type_short=info['type'][0],
                array_size=array_size,
                array_capacity=array_capacity)
    return ret

def generate_visit_struct_body(field_prefix, members):
    ret = ""
    if len(field_prefix):
        field_prefix = field_prefix + "."
    for argname, argentry, optional, structured, annotated in parse_args(members):
        if optional:
            ret += mcgen('''
visit_start_optional(m, (obj && *obj) ? &(*obj)->%(c_prefix)shas_%(c_name)s : NULL, "%(name)s", errp);
if ((*obj)->%(prefix)shas_%(c_name)s) {
''',
                         c_prefix=c_var(field_prefix), prefix=field_prefix,
                         c_name=c_var(argname), name=argname)
            push_indent()

        if structured:
            ret += mcgen('''
visit_start_struct(m, NULL, "", "%(name)s", 0, errp);
''',
                         name=argname)
            ret += generate_visit_struct_body(field_prefix + argname, argentry)
            ret += mcgen('''
visit_end_struct(m, errp);
''')
        else:
            if annotated:
                if isinstance(argentry['type'], types.ListType):
                    ret += generate_visit_array_body(argname, argentry)
            else:
                ret += mcgen('''
visit_type_%(type)s(m, (obj && *obj) ? &(*obj)->%(c_prefix)s%(c_name)s : NULL, "%(name)s", errp);
''',
                             c_prefix=c_var(field_prefix), prefix=field_prefix,
                             type=type_name(argentry), c_name=c_var(argname),
                             name=argname)

        if optional:
            pop_indent()
            ret += mcgen('''
}
visit_end_optional(m, errp);
''')
    return ret

def generate_visit_struct(name, members):
    ret = mcgen('''

void visit_type_%(name)s(Visitor *m, %(name)s ** obj, const char *name, Error **errp)
{
    if (error_is_set(errp)) {
        return;
    }
    visit_start_struct(m, (void **)obj, "%(name)s", name, sizeof(%(name)s), errp);
    if (obj && !*obj) {
        goto end;
    }
''',
                name=name)
    push_indent()
    ret += generate_visit_struct_body("", members)
    pop_indent()

    ret += mcgen('''
end:
    visit_end_struct(m, errp);
}
''')
    return ret

def generate_visit_list(name, members):
    return mcgen('''

void visit_type_%(name)sList(Visitor *m, %(name)sList ** obj, const char *name, Error **errp)
{
    GenericList *i, **prev = (GenericList **)obj;

    if (error_is_set(errp)) {
        return;
    }
    visit_start_list(m, name, errp);

    for (; (i = visit_next_list(m, prev, errp)) != NULL; prev = &i) {
        %(name)sList *native_i = (%(name)sList *)i;
        visit_type_%(name)s(m, &native_i->value, NULL, errp);
    }

    visit_end_list(m, errp);
}
''',
                name=name)

def generate_visit_enum(name, members):
    return mcgen('''

void visit_type_%(name)s(Visitor *m, %(name)s * obj, const char *name, Error **errp)
{
    visit_type_enum(m, (int *)obj, %(name)s_lookup, "%(name)s", name, errp);
}
''',
                 name=name)

def generate_visit_union(name, members):
    ret = generate_visit_enum('%sKind' % name, members.keys())

    ret += mcgen('''

void visit_type_%(name)s(Visitor *m, %(name)s ** obj, const char *name, Error **errp)
{
    Error *err = NULL;

    if (error_is_set(errp)) {
        return;
    }
    visit_start_struct(m, (void **)obj, "%(name)s", name, sizeof(%(name)s), &err);
    if (obj && !*obj) {
        goto end;
    }
    visit_type_%(name)sKind(m, &(*obj)->kind, "type", &err);
    if (err) {
        error_propagate(errp, err);
        goto end;
    }
    switch ((*obj)->kind) {
''',
                 name=name)

    for key in members:
        ret += mcgen('''
    case %(abbrev)s_KIND_%(enum)s:
        visit_type_%(c_type)s(m, &(*obj)->%(c_name)s, "data", errp);
        break;
''',
                abbrev = de_camel_case(name).upper(),
                enum = c_fun(de_camel_case(key)).upper(),
                c_type=members[key],
                c_name=c_fun(key))

    ret += mcgen('''
    default:
        abort();
    }
end:
    visit_end_struct(m, errp);
}
''')

    return ret

def generate_declaration(name, members, genlist=True):
    ret = mcgen('''

void visit_type_%(name)s(Visitor *m, %(name)s ** obj, const char *name, Error **errp);
''',
                name=name)

    if genlist:
        ret += mcgen('''
void visit_type_%(name)sList(Visitor *m, %(name)sList ** obj, const char *name, Error **errp);
''',
                 name=name)

    return ret

def generate_decl_enum(name, members, genlist=True):
    return mcgen('''

void visit_type_%(name)s(Visitor *m, %(name)s * obj, const char *name, Error **errp);
''',
                name=name)

try:
    opts, args = getopt.gnu_getopt(sys.argv[1:], "chp:o:ei:",
                                   ["source", "header", "prefix=",
                                    "output-dir=", "existing-types",
                                    "include="])
except getopt.GetoptError, err:
    print str(err)
    sys.exit(1)

output_dir = ""
prefix = ""
c_file = 'qapi-visit.c'
h_file = 'qapi-visit.h'
includes = []

do_c = False
do_h = False
existing_types = False

for o, a in opts:
    if o in ("-p", "--prefix"):
        prefix = a
    elif o in ("-o", "--output-dir"):
        output_dir = a + "/"
    elif o in ("-c", "--source"):
        do_c = True
    elif o in ("-h", "--header"):
        do_h = True
    elif o in ("-e", "--existing-types"):
        existing_types = True
    elif o in ("-i", "--include"):
        includes.append(a)

if not do_c and not do_h:
    do_c = True
    do_h = True

c_file = output_dir + prefix + c_file
h_file = output_dir + prefix + h_file

try:
    os.makedirs(output_dir)
except os.error, e:
    if e.errno != errno.EEXIST:
        raise

def maybe_open(really, name, opt):
    if really:
        return open(name, opt)
    else:
        import StringIO
        return StringIO.StringIO()

fdef = maybe_open(do_c, c_file, 'w')
fdecl = maybe_open(do_h, h_file, 'w')

fdef.write(mcgen('''
/* THIS FILE IS AUTOMATICALLY GENERATED, DO NOT MODIFY */

/*
 * schema-defined QAPI visitor functions
 *
 * Copyright IBM, Corp. 2011
 *
 * Authors:
 *  Anthony Liguori   <aliguori@us.ibm.com>
 *
 * This work is licensed under the terms of the GNU LGPL, version 2.1 or later.
 * See the COPYING.LIB file in the top-level directory.
 *
 */

#include "%(header)s"
''',
                 header=basename(h_file)))

fdecl.write(mcgen('''
/* THIS FILE IS AUTOMATICALLY GENERATED, DO NOT MODIFY */

/*
 * schema-defined QAPI visitor function
 *
 * Copyright IBM, Corp. 2011
 *
 * Authors:
 *  Anthony Liguori   <aliguori@us.ibm.com>
 *
 * This work is licensed under the terms of the GNU LGPL, version 2.1 or later.
 * See the COPYING.LIB file in the top-level directory.
 *
 */

#ifndef %(guard)s
#define %(guard)s

#include "qapi/qapi-visit-core.h"
''',
                  prefix=prefix, guard=guardname(h_file)))

if not existing_types:
    fdecl.write(mcgen('''
#include "%(prefix)sqapi-types.h"
''',
                prefix=prefix))

for include in includes:
    fdecl.write(mcgen('''
#include "%(include)s"
''',
                include=include))


exprs = parse_schema(sys.stdin)

for expr in exprs:
    if expr.has_key('type'):
        ret = generate_visit_struct(expr['type'], expr['data'])
        if not existing_types:
            ret += generate_visit_list(expr['type'], expr['data'])
        fdef.write(ret)

        if existing_types:
            ret = generate_declaration(expr['type'], expr['data'], False)
        else:
            ret = generate_declaration(expr['type'], expr['data'], True)
        fdecl.write(ret)
    elif expr.has_key('union'):
        ret = generate_visit_union(expr['union'], expr['data'])
        ret += generate_visit_list(expr['union'], expr['data'])
        fdef.write(ret)

        ret = generate_decl_enum('%sKind' % expr['union'], expr['data'].keys())
        ret += generate_declaration(expr['union'], expr['data'])
        fdecl.write(ret)
    elif expr.has_key('enum'):
        ret = generate_visit_enum(expr['enum'], expr['data'])
        fdef.write(ret)

        ret = generate_decl_enum(expr['enum'], expr['data'])
        fdecl.write(ret)

fdecl.write('''
#endif
''')

fdecl.flush()
fdecl.close()

fdef.flush()
fdef.close()
