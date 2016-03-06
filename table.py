# -*- coding: iso-8859-1 -*- #
# ======================================================================
#
# Copyright (C) 2013 Kay Schluehr (kay@fiber-space.de)
#
# t3.table.py, v B.0 2013/09/03
#
# ======================================================================


__all__ = [
    "T3Binding",
    "T3Field",
    "T3Table",
    "T3TableContext",
    "T3List",
    "T3Set",
    "T3Bitset",
    "T3Repeater",
    "T3Bitmap"]

import sys
import abc
import functools
from collections import Iterable, defaultdict
from copy import copy

import t3
import t3.pattern
from t3.pattern import T3Pattern, T3Match, MatchingFailure
from t3.number import T3Number, Hex, Bin, T3Value


MAXSIZE = 2**64

###################################### T3Binding #################################

class T3Binding(object):    
    def __init__(self, callback, name = None):
        self.obj = None
        self.name = name
        self.callback = callback

    def get_value(self):
        return self.callback(self._bound_value())

    def _compute_rest(self):
        "Function used to handle the '*' binding pattern"
        if not isinstance(self.obj, Iterable):
            raise TypeError("binding object '%s'is not iterable"%self.obj)
        if isinstance(self.obj, T3Table):
            value = []
            for i, field in enumerate(self.obj):
                if field.value_binding == self:
                    value = [field.get_value() for field in self.obj._fields[i+1:]]
                    break
            if value:
                return functools.reduce(lambda x,y: x // y, value)
            else:
                return T3Number.NULL
        else:
            raise TypeError("unable to compute rest of the object")

    def _bound_value(self):
        if self.name == "*":
            return self._compute_rest()
        elif self.name:
            return getattr(self.obj, self.name)
        else:
            return self.obj

#################################  _T3DocObject ###################################

class _T3DocObject:
    def __init__(self, t3table, callback):
        self.table = t3table
        self.callback = callback

    def __repr__(self):
        return self.callback(self.table)

######################################  T3Field ###################################

_binding_stack = []

class T3Field(object):
    '''
      O          M     O              O       O
    .--------------------------------------------------------.
    | Pattern | Name | ValueBinding | Value | ValueFormatter |
    '--------------------------------------------------------'
    '''
    def __init__(self, pattern = None,
                       name    = None,
                       value   = T3Number.NULL,
                       value_binding   = None,
                       value_formatter = None,
                       table = None):
        self.table   = table
        self.name    = name
        self.value   = value
        self.pattern = self.make_pattern(pattern)
        self.value_binding   = value_binding
        self.value_formatter = value_formatter

    def make_pattern(self, P):
        if P is not None:
            return t3.pattern.pattern_factory(P)

    def __copy__(self):
        # TODO: what about T3Lists? 
        if isinstance(self.pattern, (T3Table, t3.pattern.T3PatternPrefixed)):
            pattern = copy(self.pattern)
        else:
            pattern = self.pattern
        field = T3Field(pattern, self.name, self.value, self.value_binding, self.value_formatter)
        return field

    def __bool__(self):
        return self.value is not None

    def __nonzero__(self):
        return self.value is not None

    def reset_if_bound(self):
        if self.value_binding:
            self.value = T3Number.NULL

    def get_value(self):
        global _binding_stack
        if self.value not in (None, T3Number.NULL):
            return self.value
        if self.value_binding:
            self.value_binding.obj = self.table
            if len(_binding_stack)>10 and self.value_binding in _binding_stack:
                _binding_stack = []
                raise RuntimeError("Circular binding can't be resolved")
            _binding_stack.append(self.value_binding)
            value = self.value_binding.get_value()
            _binding_stack.pop()
            if isinstance(value, T3Table):
                return value
            if self.table:
                return self.table._coerce(value)
            else:
                return value
        return self.value

    # The following three methods are defined for convenience. They are used when either a T3Field or a list [T3Field] of
    # T3Field objects is returned. So a T3Field object is equipped with a simple list-like interface.

    def __getitem__(self, i):
        '''
        This method is defined for convenience. It is used when either a T3Field or a list [T3Field] of T3Field objects
        is returned.
        '''
        if i!=0:
            raise IndexError("field index out of range")
        return self

    def __len__(self):
        return 1

    def __iter__(self):
        return (self,)

    def __repr__(self):
        return "<t3table.T3Field '%s = %s'>"%(self.name, self.get_value())


######################################  T3Table ###################################

class T3Table(object):
    def __init__(self):
        self._fields     = []
        self._fieldnames = defaultdict(int)
        self._parent     = None

    @classmethod
    def join(cls, args):
        for arg in args:
            if not isinstance(arg, T3Table):
                inst = cls()
                cls2 = inst._coerce(arg).__class__
                return cls2.join(inst._coerce(arg) for arg in args)
        return T3List(copy(arg) for arg in args)

    def find(self, name):
        '''
        Breadth first search for a T3Field with a given ``name``.

        :param name: the name to search for
        :returns: the value of the T3Field that was searched for, None if
                  nothing was found.
        '''
        for field in self._fields:
            if field.name == name:
                return field.get_value()
        for field in self._fields:
            if isinstance(field.value, T3Table):
                res = field.value.find(name)
                if res:
                    return res

    def get_value(self):
        value = []
        for field in self._fields:
            if field:
                v = field.get_value()
                if v is not None:
                    if isinstance(v, T3Bitmap):
                        value.append(Hex(v))
                    elif isinstance(v, T3Value):
                        value.append(v.get_value())
                    else:
                        value.append(v)
        n = len(value)
        if n == 0:
            return self._get_null_value()
        elif n == 1:
            return value[0]
        else:
            return functools.reduce(lambda x,y: x // y, value)

    def add(self, pattern = 0, **kwds):
        field = self._new_field(pattern, kwds)
        self._fields.append(field)
        self._fieldnames[field.name]+=1        
        if isinstance(field.value, T3Table):
            field.value._parent = self
        field.table = self
        return self

    def match(self, data):
        data   = self._coerce(data)
        table  = copy(self)
        fields = [field for field in table._fields if field]
        P = t3.pattern.T3PatternTable(fields)
        m = P.match(data)
        if not m.fail:
            if m.rest == data:
                m.fail = True
                return m
            else:
                m.value = table
                table._auto_parent()
        return m

    def __iter__(self):
        return self._fields.__iter__()

    def __floordiv__(self, other):
        return self.__class__.join([self, other])

    def __lshift__(self, data):
        m = self.match(data)
        if m.fail:
            raise t3.pattern.MatchingFailure(m)
        else:
            return m.value

    def __getitem__(self, name):
        k = self._fieldnames.get(name, 0)
        if k == 0:
            raise AttributeError("Field with name '%s' not found"%name)
        elif k == 1:
            for field in self._fields:
                if field.name == name:
                    return field
        else:
            return list(field for field in self._fields if field.name == name)

    def __len__(self):
        return len(self._fields)

    def __nonzero__(self):
        return bool(len(self._fields))

    def __contains__(self, name):
        return name in self._fieldnames

    def __copy__(self):
        table = self.__class__()
        for field in self._fields:
            R = copy(field)
            R.table = table
            table._fields.append(R)
        table._fieldnames = self._fieldnames.copy()
        return table

    def __call__(self, __doc__ = "", **fields):
        R = self._get_root()
        memo  = {}
        root  = R._treecopy(memo)
        table = memo[id(self)]
        if __doc__:
            if hasattr(__doc__, "__call__"):
                table.__doc__ = _T3DocObject(table, __doc__)
            else:
                table.__doc__ = __doc__
        else:
            try:
                if isinstance(self.__doc__, _T3DocObject):
                    table.__doc__ = _T3DocObject(table, self.__doc__.callback)
            except AttributeError:
                pass
        for name, value in fields.items():
            if name in table._fieldnames:
                table.__setattr__(name, value)
            else:
                raise ValueError("cannot create copy of T3Table with new field '%s'"%name)
        return root

    def __getattr__(self, name):
        field = self.__getitem__(name)
        if len(field) == 1:
            return field.get_value()
        else:
            return [r.get_value() for r in field]

    def __setattr__(self, name, value):
        if name.startswith("_"):
            object.__setattr__(self, name, value)
        else:
            self._update(name, value)

    def _get_root(self):
        if self._parent is not None:
            return self._parent._get_root()
        return self

    def _coerce(self, v):
        if isinstance(v, T3Number):
            return v
        else:
            return Hex(v)

    def _get_null_value(self):
        return T3Number.NULL

    def _set_value_and_binding(self, field, v):
        if isinstance(v, T3Binding):
            field.value_binding = v
        elif v is None or isinstance(v, T3Table):
            field.value = v
        elif isinstance(v, T3Field):
            if field.name != v.name:
                raise ValueError("Cannot update field '%s' with field '%s'. Fields must have equal names"%(field.name, v.name))
            self._set_pattern(field, v.pattern)
            if v.value_binding:
                field.value = self._get_null_value()
                field.value_binding = v.value_binding
            else:
                field.value_binding = None
                self._set_value_and_binding(field, v.value)
        else:
            field.value = self._coerce(v)
        return field

    def _set_pattern(self, field, P):
        field.pattern = field.make_pattern(P)

    def _new_field(self, pattern, dct):
        if isinstance(pattern, T3Field):
            return pattern[0]
        else:
            if not dct:
                raise TypeError("T3Field:name is mandatory attribute. Cannot construct T3Field")
            ValueFormatter = None
            if len(dct)>1:
                if "__repr__" in dct:
                    ValueFormatter = dct["__repr__"]
                    del dct["__repr__"]
            if len(dct)>1:
                raise TypeError("cannot construct T3Field from dictionary %s."%dct)
            name, v = dct.items()[0]
            field = T3Field(name = name, value_formatter = ValueFormatter, table = self)
            self._set_value_and_binding(field, v)
            self._set_pattern(field, pattern)
            if field.name in T3Table.__dict__ or field.name in self.__dict__:
                raise TypeError("can't add field which has a T3Table attribute name: '%s'"%field.name)
        return field

    def _clear(self):
        # NULLs values of T3Fields with ValueBindings. This causes a re-computation
        # of values when the T3Table is updated.
        for field in self._fields:
            if field.value_binding:
                if field.value is not None:
                    field.value = self._get_null_value()
            elif isinstance(field.value, T3Table):
                field.value._clear()

    def _treecopy(self, memo):
        table = self.__copy__()
        memo[id(self)] = table
        table.__doc__ = self.__doc__
        for field in table._fields:
            if isinstance(field.value, T3Table):
                c = field.value._treecopy(memo)
                field.value = c
                c._parent = table
        return table


    def _update(self, name, value):
        '''
        :param name: name of T3Field to be updated
        :param value: value to be assigned to T3Field
        '''
        self._get_root()._clear()
        field = self.__getitem__(name)
        if len(field) == 1:
            if isinstance(value, T3List):
                value = value.get_value()
            elif isinstance(value, (list, tuple)):
                if len(value) == 1:
                    self._set_value_and_binding(field, value[0])
                else:
                    raise TypeError("cannot unpack value %s"%value)
            elif isinstance(value, T3Field):
                value.name = name
                self._set_value_and_binding(field, value)
                self._set_pattern(field, field.pattern)
                value.table = self
            elif isinstance(value, T3Table):
                self._set_value_and_binding(field, value)
                value._parent = self
            else:
                self._set_value_and_binding(field, value)
        elif isinstance(value, (list, tuple)):
            if len(value) == len(field):
                for i, r in enumerate(field):
                    self._set_value_and_binding(r, value[i])
            elif len(value)<len(field):
                if len(value) == 1:
                    raise ValueError("need more than 1 value to unpack. %d expected"%len(field))
                else:
                    raise ValueError("need more than %d values to unpack. %d expected"%(len(value), len(field)))
            else:
                raise ValueError("too many values to unpack. %d expected. %d received."%(len(field), len(value)))
        else:
            pass # TBD
        for field in self._fields:
            if field.name!=name and field.value_binding:
                field.value = self._get_null_value()

    def _auto_parent(self):
        for field in self._fields:
            if isinstance(field.value, T3Table):
                field.value._parent = self

    def _to_string_top(self, name):
        return name+":"

    def _tostring(self, indent = 0):
        S = []
        for field in self._fields:
            value = field.get_value()
            if field.value_binding:
                name = "$"+field.name
            else:
                name = field.name
            if isinstance(value, T3Table):
                S.append(indent*" "+value._to_string_top(name))
                S+=value._tostring(indent+4)
            elif value is not None:
                S.append(indent*" "+name+": " + str(value))
        return S

    def __repr__(self):        
        name = ""
        S = []
        # TODO: this clause never used. Fix it or remove it.
        if name:
            S.append(self._to_string_top(name))
            S+=self._tostring(4)
        else:
            if self._parent:
                for field in self._parent._fields:
                    if isinstance(field.value, T3Table) and id(field.value) == id(self):
                        S.append(field.value._to_string_top(field.name))
                        break
                else:
                    S.append(object.__repr__(self))
            else:
                S.append(object.__repr__(self))
            S+=self._tostring(4)
        return "\n".join(S)

################################# T3TableContext ################################

class T3TableContext(T3Table):
    _cnt = 0
    def __init__(self, name = None, default_valuetype = Hex, **options):
        super(T3Response, self).__init__(default_valuetype, **options)
        self._status = "OK"
        self._name   = name

    def __enter__(self):
        self._cnt+=1
        return self

    def __exit__(self, typ, value, tb):
        if typ:
            if typ in (AssertionError, MatchingFailure):
                self._status = "FAIL"
                self.fail_message(value)
            else:
                self._status = "ERROR"
                self.error_message(value)
        else:
            self.ok_message(value)

    def fail_message(self, value):
        traceback.print_exc()

    def error_message(self, value):
        traceback.print_exc()

    def ok_message(self, value):
        pass

######################################  T3Set ###################################

class T3Set(T3Table):
    def _set_pattern(self, field, P):
        '''
        Set P as a prefix for field.value if possible.
        '''
        if isinstance(field.value, t3.pattern.T3Pattern) and hasattr(P, "__int__"):
            try:
                P = field.value._coerce(P)
            except AttributeError:
                pass
            prefix = t3.pattern.T3PatternValue(P)
            field.pattern = t3.pattern.T3PatternPrefixed(prefix, field.value)
        else:
            super(T3Set, self)._set_pattern(field, P)

    def add_pp(self, **prefixed_pattern):
        key, value = prefixed_pattern.items()[0]
        self.add(value._fields[0].value, **prefixed_pattern)


    def match(self, data):
        data   = self._coerce(data)
        R      = data
        table  = self.__class__()
        fields = [copy(field) for field in self._fields if field]
        n      = len(fields)
        while True:
            for i, field in enumerate(fields):
                m = field.pattern.match(R)
                if not m.fail:
                    field.value = m.value
                    table.add(field)
                    R = m.rest
                    break
            else:
                return T3Match(None, R, fail = True)
            del fields[i]
            # TODO: partial match is o.k. when R is NULL?
            if fields and R:
                continue
            else:
                table._auto_parent()
                return T3Match(table, R)

######################################  T3Repeater ###################################

class T3Repeater(object):
    def __init__(self, table, minimum = 1, maximum = MAXSIZE):
        self.table = table
        self._min  = minimum
        self._max  = maximum

    def match(self, data):
        data = self.table._coerce(data)
        m    = T3Match(None, data)
        R    = m.rest
        lst  = T3List()
        i = 0
        while i<self._max:
            m = self.table.match(R)
            if m.fail:
                if i<self._min:
                    return m
                else:
                    return T3Match(lst, R)
            else:
                lst.append(m.value)
                R = m.rest
            i+=1
        return T3Match(lst, R)

    def __lshift__(self, data):
        m = self.match(data)
        if not m:
            raise MatchingFailure(m)
        else:
            return m.value

######################################  T3List ###################################

class T3List(list):
    def _coerce(self, rowvalue):
        if isinstance(rowvalue, T3Number):
            return rowvalue
        else:
            return Hex(rowvalue)

    def get_value(self):
        return Hex(self.join())

    def join(self):
        return reduce(lambda x, y: Hex(x) // Hex(y), self)

    def __floordiv__(self, other):
        if isinstance(other, T3List):
            return T3List(self+other)
        else:
            return T3List(self+[other])

    def match(self, data):
        data = self._coerce(data)
        m = T3Match(T3Number.NULL, data)
        lst = T3List()
        R = m.rest
        for table in self:            
            m = table.match(R)
            if m.fail:
                return m
            else:
                lst.append(m.value)
            R = m.rest
        return T3Match(lst, R)

    def __lshift__(self, data):
        m = self.match(data)
        if not m:
            raise MatchingFailure(m)
        else:
            return m.value

    def _repr_html_(self):
        html = ["<table>"]
        html.append("<tr>")
        for col in self:
            col = "<br>".join(str(col).split("\n"))
            html.append("<td>{0}</td>".format(col))
        html.append("</tr>")
        html.append("</table>")
        return ''.join(html)

#####################################  T3Bitmap ###################################

class T3Bitmap(T3Table):
    ## TODO: T3Table has no kwargs
    def __init__(self, **options):
        super(T3Bitmap, self).__init__(**options)
        self._bits = []

    def _coerce(self, rowvalue):
        if isinstance(rowvalue, T3Number):
            return rowvalue
        else:
            return Bin(rowvalue)

    def match(self, data):
        if not (isinstance(data, T3Number) and data.base == 2):
            bits = Bin(data)
            k = len(bits)%8
            if k:
                bits.zfill(len(bits)+8-k)
        else:
            bits = data
        m = super(T3Bitmap, self).match(bits)
        if m.rest and isinstance(data, T3Number):
            if data.base!=2:
                R  = data.__class__(m.rest.bytes(), data.base)
                m.rest = R
        return m

    def add(self, pattern = None, **kwds):
        if isinstance(pattern, int):
            k = pattern
            p = t3.pattern.T3PatternSection(k)
        elif isinstance(pattern, (str, T3Number)):
            k = int(pattern)
            p = t3.pattern.T3PatternSection(k)
        elif isinstance(pattern, T3Bitset):
            k = pattern.count
            p = pattern
        else:
            raise TypeError("cannot create bitpattern from object of type %s"%type(pattern))
        for key, value in kwds.items():
            if isinstance(value, (int, T3Number, str)):
                kwds[key] = Bin(value)
        field = self._new_field(p, kwds)
        if field.name in T3Bitmap.__dict__ or field.name in self.__dict__:
            raise TypeError("can't add field which has a T3Bitmap attribute name: '%s'"%field.name)
        field.table = self
        self._fields.append(field)
        k = self._fieldnames.get(field.name, 0)
        self._fieldnames[field.name] = k+1
        return self

    def _to_string_top(self, name):
        return name+": %s"%Bin(self)

    def get_value(self):
        value = []
        for field in self._fields:
            if field:
                p = field.pattern.count
                v = Bin(field.get_value())
                v = v.zfill(p)
                value.append(v)
        n = len(value)
        if n == 0:
            return self._get_null_value()
        elif n == 1:
            return value[0]
        else:
            return functools.reduce(lambda x,y: x // y, value)

#####################################  T3Bitset ###################################

class T3Bitset(object):
    def __init__(self, bitcount):
        self.count = bitcount
        self.fields = {}

    def __copy__(self):
        bitset = T3Bitset(self.count)
        bitset.fields = self.fields.copy()
        return bitset

    def set(self, **fields):
        for name, value in fields.items():
            b = Bin(value).zfill(self.count)
            assert len(b.digits()) == self.count, "Cannot set '%s = %s' with bitcount(%s) > %s"%(name, value, value, self.count)
            self.fields[b.digits()] = name

    def __call__(self, **fields):
        bitset = self.__copy__()
        bitset.set(**fields)
        return bitset

    def match(self, data):
        if not (isinstance(data, T3Number) and data.base == 2):
            bits = Bin(data)
            k = len(bits)%8
            if k:
                bits.zfill(len(bits)+8-k)
        else:
            bits = data

        value = bits[:self.count]
        if len(value) == self.count:
            name = self.fields.get(value.digits())
            if name:
                f = value.formatter
                value.set_formatter(lambda n: f(n) + "  ==> "+name)
                m = T3Match(value, bits[self.count:])
        else:
            m = T3Match(None, data, fail = True)

        if m.rest and isinstance(data, T3Number):
            if data.base!=2:
                R  = data.__class__(m.rest.bytes(), data.base)
                m.rest = R
        return m

########### register types at ABCs  ####################################################

# Types such as T3Bitmap or T3Set are automatically registere as subtypes of T3Table

T3Value.register(T3Table)
T3Value.register(T3Binding)
T3Value.register(T3Field)
T3Value.register(T3List)

T3Pattern.register(T3Table)
T3Pattern.register(T3Repeater)
T3Pattern.register(T3List)
T3Pattern.register(T3Bitset)


########################################################################################
#
#        Tests
#
########################################################################################

def _build_tlv():
    def update_len(v):
        # v = binding.bound_value()
        if v is not None:
            try:
                n = len(v.get_value())
            except AttributeError:
                n = len(v)
            k = Hex(n)
            if len(k) == 1:
                if k>=0x80:
                    return 0x81 // k
                else:
                    return k
            else:
                return (0x80 | len(k)) // k

    def tag_size(tlv, data):
        if data[0] & 0x1F == 0x1F:
            return 2
        else:
            return 1

    def len_size(tlv, data):
        if data[0] & 0x80 == 0x80:
            lenlen = data[0] & 0x0F
            return 1+lenlen
        return 1

    def value_size(tlv, data):
        if isinstance(tlv.Value, t3.pattern.T3Pattern):
            return tlv.Value
        if tlv.Len[0] & 0x80 == 0x80:
            return int(tlv.Len[1:])
        else:
            return int(tlv.Len)

    Tlv = T3Table()
    Tlv.__doc__ = "TLV data structure"

    Tlv.add(tag_size, Tag = "A5")
    Tlv.add(len_size, Len = T3Binding(update_len, "*"))
    Tlv.add(value_size, Value = "89 89")

    return Tlv

def test_tlv():    
    print("call: test_tlv()")
    Tlv = _build_tlv()
    Tlv << "A7 02 03 05 06"
    assert Tlv.get_value() == "A5 02 89 89"
    assert Hex(Tlv) == "A5 02 89 89"
    assert Tlv.Len == 2
    assert Tlv.Value == "89 89"
    Tlv.Value = "00"*0x80
    # print len(Tlv._fields[2].table._fields)
    Tlv << "A7 02 03 05 06"
    assert Tlv.Len == "81 80"

    Tlv2 = copy(Tlv)
    Tlv2.Value = "00"
    assert Tlv2.Len == 1

    Tlv3 = Tlv2(Tag = "A6")
    assert Tlv3.Tag == 0xA6

    try:
        Tlv3.add(1, _fields = 0)
        assert False, "TypeError exception not raised"
    except TypeError:
        pass

    Tlv2.Value = Tlv3
    assert Hex(Tlv2.Value(Value = "89 AF")) == 'A5 04 A6 02 89 AF'

    TlArray = T3Table()
    TlArray.add(Tag = 0x9A)
    TlArray.add(Len = 0x04)
    TlArray.add(Tag = 0x5F0A)
    TlArray.add(Len = 0x02)
    TlArray.add(Tag = 0x8A)
    TlArray.add(Len = 0x08)

    assert len(TlArray["Len"]) == 3
    assert TlArray.Len == [0x04, 0x02, 0x08]
    assert len(TlArray["Tag"]) == 3
    assert TlArray.Tag == [0x9A, 0x5F0A, 0x8A]

    dol = TlArray(Tag = [0x95, 0x5F0A, 0x8A])

    assert len(list(zip(dol.Tag, dol.Len))) == 3

    Tlv4 = Tlv << "A7 02 03 05 06"

    assert Tlv4.Tag  == "A7"
    assert Tlv4.Len  == "02"
    assert Tlv4.Value == "03 05"

    Tlv4.Value = "03 05 06"
    assert Tlv4.Len == "03"
    Tlv4.Value = "03 05 06 07"
    assert Tlv4.Len == "04"

    Tlv5 = Tlv4(Len = T3Field(pattern = '05', value = 0x05))
    assert (Tlv5 << 'A0 05 01 02 03 04 05').Len == '05'

    try:
        Tlv5 << "A7 04 01 02 03 04"
    except t3.pattern.MatchingFailure:
        pass
    else:
        assert False, "MatchingFailure exception not raised"

    A = T3Table()
    A.add(B = 0x00)
    A.add(C = 0x01)
    A.C = A()
    assert Hex(A.C(B = 0x78)) == '00 78 01'

    assert copy(A.C).B == 0x00
    assert copy(A.C).C == 0x01

    RApdu = T3Table()
    RApdu.add("*", Data = '00')
    RApdu.add(1, Le = None)
    RApdu.add(2, SW = '00 00')

    Tlv.Value = "00 00 00"

    r = RApdu << '00 01 02 00 67 90 00'
    assert r.SW == 0x9000
    assert r.Data == '00 01 02 00 67'
    r = RApdu(Le="00") << '00 01 02 00 67 90 00'
    assert r.SW == 0x9000
    assert r.Le == "67"
    assert r.Data == '00 01 02 00'
    T1 = Tlv(Tag = 0x78)
    T2 = Tlv(Tag = 0xA6)
    ts = T3Set()
    ts.add(0x78, T1 = T1)
    ts.add(0xA6, T2 = T2)
    tree = ts << '78 01 06 A6 03 01 02 04'
    assert tree.T1.Tag == '78'
    assert tree.T2.Tag == 'A6'
    assert Hex(tree.T1(Value = 0x07)) == '78 01 07 A6 03 01 02 04'
    tree = ts << 'A6 03 01 02 04 78 01 06'
    assert Hex(tree) ==  'A6 03 01 02 04 78 01 06'
    tree.T1.Value = '05 06'
    assert Hex(tree) == 'A6 03 01 02 04 78 02 05 06'


def test_set():
    print("call: test_set()")
    Tlv = _build_tlv()
    X1 = T3Set()
    X1.add(0x78, F_87 = Tlv(Tag = 0x78))
    X1.add(0xA6, F_A6 = Tlv(Tag = 0xA6, Value = 'AA'))

    X = X1()
    H = Hex(X)
    X << H

    X2 = T3Set()
    X2.add(0x9F01, F_9F01 = Tlv(Tag = 0x9F01))
    X2.add(0x9F02, F_9F02 = Tlv(Tag = 0x9F02))
    X2.add(0x9F03, F_9F03 = Tlv(Tag = 0x9F03))

    Y1 = Tlv(Tag = 0x8C, Value = X1)
    Y2 = Tlv(Tag = 0x8D, Value = X2)

    Y = T3Set()
    Y.add(0x8C, F_8C = Y1)
    Y.add(0x8D, F_8D = Y2)

    T = T3Set()
    T.add(0xA5, Value = Tlv(Tag = 0xA5, Value = Y))

    F_8C = T.find("F_8C")
    n = F_8C.Len
    F_A6 = T.find("F_A6")
    assert len(F_A6.Value) == 1
    F_A6.Value = "01 02 03 04"
    assert F_8C.Len == n + 3

    R = F_A6(Value = "01 02 03 04 05")
    assert F_8C.Len == n + 3
    assert R.find("F_8C").Len == n + 4
    F_A6.Value = "01"

    R = T << Hex(T)
    assert Hex(T) == Hex(R)

    R2 = R()
    R3 = R2 << Hex(R2)
    assert Hex(R2) == Hex(R3)

    F_8C = R.find("F_8C")
    n = F_8C.Len
    F_A6 = R.find("F_A6")
    assert len(F_A6.Value) == 1
    F_A6.Value = "01 02 03 04"
    assert F_8C.Len == n + 3

    R = F_A6(Value = "01 02 03 04 05")
    assert F_8C.Len == n + 3
    assert R.find("F_8C").Len == n + 4

    R = T << 'A5 1F 8C 09 A6 02 00 00 78 03 00 00 01 8D 12 9F 01 03 00 00 00 9F 02 03 00 00 00 9F 03 03 00 00 00'

    assert Hex(R.find("F_8C")) == "8C 09 A6 02 00 00 78 03 00 00 01"
    assert Hex(R.find("F_8C").find("F_A6")) == "A6 02 00 00"
    assert Hex(R.find("F_8C").find("F_87")) == "78 03 00 00 01"

    R.find("F_8C").find("F_87").Value = "00 00 01 02"

    assert Hex(R.find("F_8C")) == "8C 0A A6 02 00 00 78 04 00 00 01 02"
    #print T3Number(0x8CC010,2)
    T = Tlv(Tag = 0x78, Value = 0x65) // Tlv(Tag = 0xA6, Value = 0x62)
    assert Hex(T) == Hex(Tlv(Tag = 0x78, Value = 0x65)) // Hex(Tlv(Tag = 0xA6, Value = 0x62))

    X1 = T3Set()
    X1.add_pp(F_87 = Tlv(Tag = 0x78))
    X1.add_pp(F_A6 = Tlv(Tag = 0xA6, Value = 'AA'))
    X = X1()
    H = Hex(X)
    assert Hex(X << H) == H

def test_atr():
    print("call: test_atr()")
    def get_frequency(value):
        "FI     Value F     f max [MHz]"
        S ='''
        0000    372         4
        0001    372         5
        0010    558         6
        0011    744         8
        0100    1116        12
        0101    1488        16
        0110    1860        20
        0111    RFU         RFU
        1000    RFU         RFU
        1001    512         5
        1010    768         7.5
        1011    1024        10
        1100    1536        15
        1101    2048        20
        1110    RFU         RFU
        1111    RFU         RFU
        '''.split("\n")
        for s in S:
            s = s.strip()
            if s:
                code, Value_F, frequency = [r.strip() for r in s.split(" ") if r.strip()]
                if Bin(code) == value:
                    return (Value_F, frequency)

    def format_FI(value):
        value_formatter = value.formatter
        def formatter():
            Value_F, frequency = get_frequency(value)
            return value_formatter() + "  ==> Fi: %s; f max [MHz]: %s"%(Value_F, frequency)
        return formatter

    def format_DI(value):
        value_formatter = value.formatter

        S = '''
        0000    RFU
        0001    1
        0010    2
        0011    4
        0100    8
        0101    16
        0110    32
        0111    RFU
        1000    12
        1001    20
        1010    RFU
        1011    RFU
        1100    RFU
        1101    RFU
        1110    RFU
        1111    RFU
        '''.split("\n")
        def formatter():

            for s in S:
                s = s.strip()
                if s:
                    code, D = [r.strip() for r in s.split(" ") if r.strip()]
                    if Bin(code) == value:
                        return value_formatter()+ "  ==> D: %s"%(D,)
        return formatter

    def format_Protocol(value):
        value_formatter = value.formatter
        def formatter():
            n = T3Number(value, 10).number()
            if n in (0,1,14):
                return value_formatter()+ "  ==> T = %s"%n
            else:
                return value_formatter()+ "  ==> RFU"
        return formatter


    def interface_char_size(field, bit):

        def compute_len(atr, data):
            try:
                B = getattr(atr, field)
                if B is not None:
                    mask = 1<<(bit-1)
                    if Hex(B) & mask == mask:
                        if bit == 8:
                            n = int(field[-1])+2
                            fields = [{"TD%s_used"%n: 0},
                                      {"TC%s_used"%n: 0},
                                      {"TB%s_used"%n: 0},
                                      {"TA%s_used"%n: 0}]
                            return (T3Bitmap().add(1, **fields[0])
                                              .add(1, **fields[1])
                                              .add(1, **fields[2])
                                              .add(1, **fields[3])
                                              .add(4, Protocol = 0, __repr__ = format_Protocol))
                        elif (field, bit) == ("T0", 5):
                            return T3Bitmap().add(4, FI = 0, __repr__ = format_FI).add(4, DI = 0, __repr__ = format_DI)
                        return 1
                    else:
                        return 0
                return 0
            except AttributeError:
                return 0

        return compute_len

    def historicals(atr, data):
        return atr.T0.nbr_of_historicals

    def tck(atr, data):
        if data:
            return 1
        else:
            return 0

    ATR = T3Table()
    ATR.add('3B', TS = '3B')
    ATR.add(T3Bitmap().add(1, TD1_used = 0)
                      .add(1, TC1_used = 0)
                      .add(1, TB1_used = 0)
                      .add(1, TA1_used = 0)
                      .add(4, nbr_of_historicals = 0),
            T0 = 0)
    ATR.add(interface_char_size("T0", 5), TA1 = '00')
    ATR.add(interface_char_size("T0", 6), TB1 = '00')
    ATR.add(interface_char_size("T0", 7), TC1 = '00')
    ATR.add(interface_char_size("T0", 8), TD1 = '00')

    ATR.add(interface_char_size("TD1", 5), TA2 = '00')
    ATR.add(interface_char_size("TD1", 6), TB2 = '00')
    ATR.add(interface_char_size("TD1", 7), TC2 = '00')
    ATR.add(interface_char_size("TD1", 8), TD2 = '00')

    ATR.add(interface_char_size("TD2", 5), TA3 = '00')
    ATR.add(interface_char_size("TD2", 6), TB3 = '00')
    ATR.add(interface_char_size("TD2", 7), TC3 = '00')
    ATR.add(interface_char_size("TD2", 8), TD3 = '00')

    ATR.add(interface_char_size("TD3", 5), TA4 = '00')
    ATR.add(interface_char_size("TD3", 6), TB4 = '00')
    ATR.add(interface_char_size("TD3", 7), TC4 = '00')
    ATR.add(interface_char_size("TD3", 8), TD4 = '00')

    ATR.add(historicals, HistoricalCharacters = '00 00 00 00')
    ATR.add(tck, TCK = '00')

    atr = ATR << '3B FF 18 00 FF 81 31 FE 45 65 63 11 05 40 02 50 00 10 55 10 03 03 05 00 43'
    # print atr
    assert atr.TS == 0x3B
    assert atr.TD1.TD2_used == 1
    atr2 = atr.TD1(TD2_used = 0)
    assert atr2.TD1.TD2_used == 0
    #print atr2
    assert Hex(atr) == '3B FF 18 00 FF 81 31 FE 45 65 63 11 05 40 02 50 00 10 55 10 03 03 05 00 43'
    try:
        ATR << '3E FF 18 00 FF 81 31 FE 45 65 63 11 05 40 02 50 00 10 55 10 03 03 05 00 43'        
    except MatchingFailure:
        pass
    else:
        assert False, "MatchingFailure exception not raised"



def test_apdu():
    print("call: test_apdu()")
    def data_len(Data):
        n = len(Data)
        if n<=0xFF:
            return Hex(n)
        else:
            raise ValueError("Data length must be <= 0xFF")

    Apdu = T3Table()
    Apdu.add(1, Cla  = 0x00)
    Apdu.add(1, Ins  = 0xA4)
    Apdu.add(1, P1   = 0x00)
    Apdu.add(1, P2   = 0x00)
    Apdu.add(1, Lc   = T3Binding(data_len, "Data"))
    Apdu.add("*", Data = 0x00)

    Apdu.Data = "3F 00"
    assert Apdu.Lc == 2
    Apdu.Data = "3F 00 DF 01 EF 01"
    assert Apdu.Lc == 6
    assert Hex(Apdu) == "00 A4 00 00 06 3F 00 DF 01 EF 01"

    Select_MF = Apdu << '00 A4 00 00 02 3F 00 00 00 00'
    assert Select_MF.Lc == 2
    Select_MF.Data = '90 89 78'
    assert Select_MF.Lc == 3
    Select_MF = Apdu << '00 A4 00 00 02 3F 00 00 00 00'
    Select_MF.P1 = 0x01
    assert Select_MF.Lc == 5
    assert Select_MF.Data == '3F 00 00 00 00'

    def data_size(table, data):
        return table.Lc.number()

    Apdu = T3Table()
    Apdu.add(1, Cla  = 0x00)
    Apdu.add(1, Ins  = 0xA4)
    Apdu.add(1, P1   = 0x00)
    Apdu.add(1, P2   = 0x00)
    Apdu.add(1, Lc   = T3Binding(data_len, "Data"))
    Apdu.add(data_size, Data = 0x00)
    Apdu.__doc__ = "APDU"
    Select_MF = Apdu << '00 A4 00 00 02 3F 00 00 00 00'
    assert Select_MF.Data == '3F00'

    Select = Apdu()
    assert Select.__doc__ == "APDU"
    Select = Apdu(__doc__ = "SELECT")
    assert Select.__doc__ == "SELECT"

def test_empty_match():
    print("call: test_empty_match()")
    t = T3Table().add(r = 0).add(s = 0)
    m = t.match("89 67")
    assert m.fail
    try:
        t << "89 67"
        assert 1 == 0
    except MatchingFailure:
        pass

def test_list():
    print("call: test_list()")
    Tlv = _build_tlv()
    t = T3Table().add(T3Table().add(1, s = 0).add(1, r = 0), u = 0)

    assert (t << "89 67").u.r == 0x67
    assert (t << "89 67").u.s == 0x89

    tr = T3Repeater(t, 2, 4)
    h = Hex("27 82 72 87 28 72 67 88 00 70")
    v = tr << h
    assert isinstance(v, T3List)
    assert Hex(v[1].u) == "72 87"
    assert Hex(v[0].u.r) == "82"
    assert len(v) == 4
    assert Hex(v) == h[:8]
    tr = T3Repeater(t)
    v = tr << h
    assert len(v) == 5
    assert Hex(v) == h

    Tlv(Value = Tlv // Tlv)

def test_btmp():
    print("call: test_btmp()")    
    btmp = T3Bitmap()
    btmp.add(2, A = 1)
    btmp.add(6, B = 1)
    R = btmp << 0x8CC010
    assert R.A == 2
    assert R.B == 0xC
    btmp = btmp(B = T3Field(pattern = 8))
    R = btmp << 0x8CC010
    assert R.A == 2
    assert R.B == 0x33
    btmp = btmp(B = T3Field(pattern = 15))
    R = btmp << 0x8CC010
    assert R.A == 2
    assert R.B == Hex('19 80')

    btmp = T3Bitmap()
    btmp.add(6, A = 1)
    btmp.add(15, B = 1)
    btmp.add(3, C = 1)
    R = btmp << 0x8CC011
    assert R.A == 0x23
    assert R.B == 0x1802
    assert R.C == 1

    T = T3Table()
    T.add(T3Bitmap().add(5, f1 = 0)
                    .add(3, f2 = 0)
                    .add(4, f3 = 0)
                    .add(4, f4 = 0),
          A = 0
    )
    T.add(T3Bitmap().add(2, f1 = 0)
                    .add(5, f2 = 0),
          B = 0
    )

    B = T << Bin('111 1000 0100 0101 0011 0100')
    assert B.A.f1 == 0x1E

    B = T << '78 45 34'
    assert B.A.f1 == 0x0F
    T.add(1, C = 0)
    B = T << '78 45 34 78'
    # print B

    BerClass = T3Bitset(2)
    BerClass.set(UniversalClass       = '00')
    BerClass.set(ApplicationClass     = '01')
    BerClass.set(ContextSpecificClass = '10')
    BerClass.set(PrivateClass         = '11')

    PC = T3Bitset(1)
    PC.set(Primitive   = 0)
    PC.set(Constructed = 1)

    BerTag = T3Bitmap()
    BerTag.add(BerClass, BerClass = 0)
    BerTag.add(PC, P1 = 1)
    BerTag.add(5, TagNumber = 0)

    tag = BerTag << 0x1F
    print tag
    

def test_cyclic():    
    T = T3Table()    
    T.add(1, A = T3Binding(len, "A"))
    T << "01"
    try:
        T.A
    except RuntimeError as e:
        assert str(e) == "Circular binding can't be resolved", str(e)

    T = T3Table()    
    T.add(1, A = T3Binding(len, "B"))
    T.add(1, B = T3Binding(len, "A"))
    T << "01 01"
    try:
        T.A
    except RuntimeError as e:        
        assert str(e) == "Circular binding can't be resolved", str(e)

    T = T3Table()    
    T.add(1, A = T3Binding(len, "B"))
    T.add(1, B = T3Binding(len, "C"))
    T.add(1, C = T3Binding(len, "D"))
    T.add(1, D = T3Binding(len, "E"))
    T.add(1, E = T3Binding(len, "F"))
    T.add(1, F = T3Binding(len, "G"))
    T.add(1, G = T3Binding(len, "H"))
    T.add(1, H = T3Binding(len, "I"))
    T.add(1, I = T3Binding(len, "J"))
    T.add(1, J = T3Binding(len, "K"))
    T.add(1, K = T3Binding(len, "L"))
    T.add(1, L = "01")

    T << "01"*12
    assert T.A == 1

    T.L = "01 02 03"
    assert T.K == 3
    assert T.A == 1

    # now make T circular
    U = T(L = T3Field(pattern = 1, name = "L", value_binding = T3Binding(len, "A")))
    try:
        U.A
    except RuntimeError as e:        
        assert str(e) == "Circular binding can't be resolved", str(e)
    

if __name__ == '__main__':
    test_tlv()
    test_set()
    test_apdu()
    test_empty_match()
    test_list()
    test_atr()
    test_btmp()
    test_cyclic()
