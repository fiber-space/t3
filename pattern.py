# ======================================================================
#
# Copyright (C) 2016 Kay Schluehr (kay@fiber-space.de)
#
# pattern.py, v B.0 2016/03/03
#
# ======================================================================

__all__ = ["pattern_factory",
           "MatchingFailure",
           "T3Match",
           "T3Pattern",           
           "T3PatternAny",
           "T3PatternAlt",
           "T3PatternTable",
           "T3PatternFunction",
           "T3PatternValue",
           "T3PatternSection",
           "T3PatternPrefixed"]

import abc
from copy import copy
from t3.util.six import add_metaclass

# TODO: It must be prevented that None is accidentally assigned as a value because it disables a field.

@add_metaclass(abc.ABCMeta)
class T3Pattern(object):
    @abc.abstractmethod
    def match(self, data, table = None):
        pass

# for convenience
T3Matcher = T3Pattern

def pattern_factory(arg):
    if isinstance(arg, T3Pattern):
        return arg
    elif hasattr(arg, "__call__"):
        return T3PatternFunction(arg)
    elif arg == "*":
        return T3PatternAny()
    elif hasattr(arg, "__int__"):
        return T3PatternSection(arg)
    elif isinstance(arg, str):
        if "|" in arg:
            return T3PatternAlt(*[T3PatternValue(part) for part in arg.split("|")])
        else:
            return T3PatternValue(arg)
    else:
        return T3PatternValue(arg)

class T3Match(object):
    def __init__(self, value, rest, fail = False):
        self.value = value
        self.rest  = rest
        self.fail  = fail

    def __eq__(self, other):
        if isinstance(other, T3Match):
            return self.value == other.value and self.rest == other.rest
        return False

    def __repr__(self):
        return "<T3Match <%s:%s>>"%(self.value, self.rest)

class MatchingFailure(Exception):
    def __init__(self, t3match):
        self.t3match = t3match

    def __str__(self):
        if self.t3match.value is None:
            return "Failed to match data at pos 0"
        else:
            return "Failed to match data at pos %s"%len(self.t3match.value)



class T3PatternTable(T3Pattern):
    '''
    T3PatternTable(fields).match(data) -> (field1.value = field1.match(data).value,
                                           field2.value = field2.match(field1.match(data).rest),
                                           field3.value = field3.match(field2.match(field1.match(data).rest).rest),
                                           ...
                                           )
    '''
    def __init__(self, fields):
        self.fields = fields

    def match(self, data):
        field = self.fields[0]
        P = field.pattern
        if len(self.fields)>1:
            Q = T3PatternTable(self.fields[1:])
            if isinstance(P, T3PatternAny):
                for k in range(len(data)-1, -1, -1):
                    m = Q.match(data[k:])
                    if not m.fail:
                        field.value = data[:k]
                        m.value = data
                        return m
                return T3Match(None, data, fail = True)
            else:
                if isinstance(P, T3PatternFunction):
                    m = P.match(data, field.table)
                else:
                    m = P.match(data)
                if m.fail:
                    return m
                else:
                    field.value = m.value
                    m_Q = Q.match(m.rest)
                    if m_Q.fail:
                        if m_Q.value is None:
                            m_Q.value = m.value
                        else:
                            m_Q.value = data[:len(m.value)+len(m_Q.value)]
                    else:
                        m_Q.value = data[:len(m.value)+len(m_Q.value)]
                    return m_Q
        else:
            if isinstance(P, T3PatternFunction):
                m = P.match(data, field.table)
            else:
                m = P.match(data)
            if not m.fail:
                field.value = m.value
            return m

class T3PatternFunction(T3Pattern):
    '''
    T3PatternFunction(f).match(data, table) -> pattern_factory(f(table, data)).match(data)
    '''
    def __init__(self, getpattern):
        super(T3PatternFunction, self).__init__()
        self.getpattern = getpattern

    def match(self, data, table):
        P = self.getpattern(table, data)
        Q = pattern_factory(P)
        return Q.match(data)

class T3PatternSection(T3Pattern):
    '''
    T3PatternSection(k).match(data) -> T3Match(data[:k], data[k:])
    '''
    def __init__(self, count):
        super(T3PatternSection, self).__init__()
        self.count = count

    def match(self, data):
        value = data[:self.count]
        if len(value) == self.count:
            return T3Match(value, data[self.count:])
        else:
            return T3Match(None, data, fail = True)

class T3PatternAny(T3Pattern):
    '''
    T3PatternAny().match(data) -> T3Match(data, None)
    '''
    def match(self, data):
        return T3Match(data, None)

class T3PatternAlt(T3Pattern):
    '''
    T3PatternAlt(patterns).match(data) -> find pattern.match(data) for pattern in patterns
    '''
    def __init__(self, *patterns):
        self.patterns = patterns

    def match(self, data):
        for pattern in self.patterns:
            m = pattern.match(data)
            if not m.fail:
                return m
        return T3Match(None, data, fail = True)

class T3PatternValue(T3Pattern):
    '''
    T3PatternValue(value).match(data) -> T3Match(value, data[len(value):])
    '''
    def __init__(self, value):
        try:
            iter(value)
        except TypeError:
            raise TypeError("value not iterable. Cannot convert object of type '%s' into T3PatternValue"%str(type(value)))
        self.value = value

    def match(self, data):
        try:
            value = data.__class__(self.value)
        except TypeError:
            value = self.value
        k = len(value)
        if data[:k] != value:
            return T3Match(None, data, fail = True)
        return T3Match(data[:k], data[k:])

class T3PatternPrefixed(T3Pattern):
    '''
    T3PatternPrefixed(pfx, pattern).match(data) -> pattern.match(data) if pfx.match(data)
    '''
    def __init__(self, prefix, pattern):
        self.prefix  = prefix
        self.pattern = pattern

    def __copy__(self):
        return T3PatternPrefixed(self.prefix, copy(self.pattern))

    def match(self, data):
        m = self.prefix.match(data)
        if m.fail:
            return m
        else:
            return self.pattern.match(data)


