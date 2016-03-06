# ======================================================================
#
# Copyright (C) 2013 Kay Schluehr (kay@fiber-space.de)
#
# t3number.py, v B.0 2013/09/03
#
# ======================================================================

__all__ = ["T3Number", "T3NumberFormatter", "Hex", "Bin", "Bcd", "NULL"]

from array import array
import functools
import abc
import sys
from t3.util.six import add_metaclass

if sys.version > '3':
    long = int

DIGIT_U = "0123456789ABCDEF"
DIGIT_L = "0123456789abcdef"
DIGITS_PER_BYTE = "xx864443333333332"

@add_metaclass(abc.ABCMeta)
class T3Value:
    @abc.abstractmethod
    def get_value(self):
        pass

def log2base(n):
    r = 0
    while True:
        n = n>>1
        if n == 0:
            break
        r+=1
    return r

class T3NumberFormatter:
    def __init__(self, tabular = False):
        self.tabular = tabular
        self.block   = dict((n, len(T3Number(256, n).digits())) for n in range(2, 16))

    def _split_to_blocks(self, s, block_size, front = True):
        n = len(s)
        blocks = []
        if front:
            i = n % block_size
            if i:
                blocks.append(s[:i])
        else:
            i = 0
        while i<n:
            blocks.append(s[i:i+block_size])
            i+=block_size
        return blocks

    def format_hex(self, number):
        lines = []
        if self.tabular:
            for line in self._split_to_blocks(
                            self._split_to_blocks(number.digits(), 2), 
                            16, front = False):
                lines.append(" ".join(line))
            n = len(number.digits())
            if n<256:
                k = 3
            else:
                k = 4
            L = []
            h = 0x10
            for i, line in enumerate(lines):
                pre = " "*4
                L.append(pre+line)
            return "\n".join(L)
        else:
            return " ".join(self._split_to_blocks(number.digits(), 2))

    def format_bcd(self, number):
        return "n'"+" ".join(self._split_to_blocks(number.digits(), 2))

    def format_bin(self, number):
        lines = []
        k = len(number.digits())%8
        digits = number.digits()
        for line in self._split_to_blocks(self._split_to_blocks(digits, 8), 8):
            lines.append(" ".join(line))
        return "\n".join(lines) + " (h'%s)"%(Hex(number),)

    def format_dec(self, number):
        s = number.digits()
        if len(s)<4:
            return s
        k = len(s)%3
        if k:
            return s[:k]+"."+'.'.join(self._split_to_blocks(number.digits()[:-k], 3))
        else:
            return '.'.join(self._split_to_blocks(number.digits(), 3))

    def format_t3num(self, number):
        d = self.block[number.base-1]
        s = number.digits()
        if len(s)<d:
            return s
        k = len(s)%3
        return number._num_prefix()+''.join(self._split_to_blocks(number.digits(), d))

    def __call__(self, number):
        sign  = "-" if int(number)<0 else ""
        if isinstance(number, Hex):
            n = self.format_hex(number)
        elif isinstance(number, Bin) or number.base == 2:
            n = self.format_bin(number)
        elif isinstance(number, Bcd):
            n = self.format_bcd(number)
        else:
            n = self.format_t3num(number)
        return sign+n

############################  T3Number  ################################################

class T3Number(object):
    '''
    A T3Number is a triple (N, S, b) consisting of

        * an integer N
        * a numeral string S
        * the numeral base b of S or the radix

    S is a numeral representation of N. A T3Number is a *hybrid type* which means that it acts like
    an
    '''
    _convertible_types = (int, long, str, array)
    formatter = None

    def __init__(self, data, base = 16):
        if 2<=base<=16:
            self.base = base
        else:
            ValueError("base must be in {2..16}. Base value '%s' found"%base)
        self._str = ''
        self._int = -1

        if data is not None:
            if isinstance(data, T3Value):
                data = data.get_value()
            if isinstance(data, T3Number):
                self._from_t3number(data, base)
                self._preserve_leading_zeros(data, base)
            elif isinstance(data, str):
                self._from_string(data, base)
            elif isinstance(data, (int, long)):
                self._from_integer(data, base)
            elif isinstance(data, array):
                self._from_array(data, base)
            else:
                raise TypeError("illegal argument type %s"%type(data))

    def _preserve_leading_zeros(self, data, base):
        '''
        This function is used preserve leading zeros of a number represented in 
        base B1 when converted into base B2.
        '''
        if data.base == base:
            return
        k = 0
        for c in data._str:
            if c == '0':
                k+=1
            else:
                break
        K2 = int(DIGITS_PER_BYTE[data.base])
        if k>=K2:
            K1  = int(DIGITS_PER_BYTE[base])
            n = len(self._str)
            p = K1*(k//K2)
            r = (n + p) % K1
            if r:
                p += (K1-r)
            if self._int == 0:
                self._str = "0"*p
            else:
                self._str = "0"*p+self._str

    def set_formatter(self, formatter):
        self.formatter = formatter

    def _num_prefix(self):
        return str(self.base)+"'"

    def _from_t3number(self, N, base):
        if base == N.base:
            self._str = N._str
            self._int = N._int
        else:
            self._from_integer(N._int, base)

    def _from_string(self, S, base):
        digits = []
        begin = ''
        for i, c in enumerate(S):
            if c in ("'", '"'):
                if i:
                    S = S[i:]
                break
        for c in S:
            if begin:
                if c == '}':
                    begin = ''
                else:
                    n = ord(c)
                    s = self.__class__(n, base)._str
                    digits.append(s)
            elif c in DIGIT_U or c in DIGIT_L:
                digits.append(c.upper())
            elif c == '{':
                begin = c
        if begin:
            raise ValueError("Missing terminating brace '}'")
        self._str = ''.join(digits)
        self._int = int(self._str, base)

    def _from_integer(self, n, base):
        self._int = n
        if n == 0:
            self._str = "0"
        else:
            digits = []            
            if n<0:
                raise TypeError("no encoding for negative numbers")
            while n>0:
                n, r = divmod(n, base)
                digits.append(DIGIT_U[r])
            self._str = "".join(digits[::-1])

    def _from_array(self, a, base):
        if a.typecode == 'b':
            bytes = [(x+256 if x<0 else x) for x in a]
        elif a.typecode == 'B':
            bytes = a.tolist()
        else:
            raise TypeError("typecode of array must be 'b' or 'H'")
        S = []
        for b in bytes:
            if 0<=b<16:
                S.append("0"+DIGIT_U[b])
            else:
                S.append(hex(b)[2:].upper())
        s = ''.join(S)
        n = T3Number(s, 16)
        self._int = n._int
        if base == 16:
            self._str = n._str
        else:
            self._str = T3Number(n._int, base)._str

    def _maxfill(self, other):
        if other.base == self.base:
            return self.base, max(len(self._str), len(other._str)), self.__class__
        if other.base>self.base:
            return other.base, len(other._str), other.__class__
        elif self.base>other.base:
            return self.base, len(self._str), self.__class__

    def _bits_per_item(self):
        return log2base(self.base)

    def __hash__(self):
        return self._int

    def __len__(self):
        return len(self._str)

    def concat(self, other):
        return self.__floordiv__(other)

    def __floordiv__(self, other):
        '''
        Concatenation operator
        '''
        if isinstance(other, T3Number):
            if other is T3Number.NULL:
                return self
            if self is T3Number.NULL:
                return other
            elif other.base == self.base:
                if self._int>=0 and other._int>=0:
                    return self.__class__(self._str + other._str, self.base)
                else:
                    raise TypeError("Cannot concatenate negative T3Numbers")
            else:
                raise TypeError("Cannot concatenate objects of types '%s' and '%s' which have different number bases"%(self.__class__.__name__, other.__class__.__name__))
        else:
            return self.__floordiv__(T3Number(other, self.base))

    def __rfloordiv__(self, other):
        return self.__class__(other, self.base).__floordiv__(self)

    def __nonzero__(self):
        return self._int != 0

    def __radd__(self, other):
        return self.__class__(other, self.base).__add__(self)

    def __add__(self, other):
        if isinstance(other, T3Number):
            base, fill, cls = self._maxfill(other)
            n = cls(self._int + other._int, base)
            n.zfill(fill)
            return n
        else:
            return self.__add__(T3Number(other, self.base))

    def __rmul__(self, other):
        return self.__class__(other, self.base).__mul__(self)


    def __mul__(self, other):
        if isinstance(other, T3Number):
            base, fill, cls = self._maxfill(other)
            n = cls(self._int * other._int, base)
            n.zfill(fill)
            return n
        else:
            return self.__mul__(T3Number(other, self.base))

    def __rsub__(self, other):
        return self.__class__(other, self.base).__sub__(self)


    def __sub__(self, other):
        if isinstance(other, T3Number):
            base, fill, cls = self._maxfill(other)
            k = max(0, self._int - other._int)
            n = cls(k, base)
            n.zfill(fill)
            return n
        else:
            return self.__sub__(T3Number(other, self.base))

    def __rmod__(self, other):
        return self.__class__(other, self.base).__mod__(self)

    def __mod__(self, other):
        if isinstance(other, T3Number):
            base, fill, cls = self._maxfill(other)
            n = cls(self._int % other._int, base)
            n.zfill(fill)
            return n
        else:
            return self.__mod__(T3Number(other, self.base))

    def __rrshift__(self, other):
        return self.__class__(other, self.base).__rshift__(self)

    def __rshift__(self, other):
        if isinstance(other, T3Number):
            base, fill, cls = self._maxfill(other)
            n = cls(self._int >> other._int, base)
            n.zfill(fill)
            return n
        else:
            return self.__rshift__(T3Number(other, self.base))

    def __rlshift__(self, other):
        return self.__class__(other, self.base).__lshift__(self)

    def __lshift__(self, other):
        if isinstance(other, T3Number):
            base, fill, cls = self._maxfill(other)
            n = cls(self._int << other._int, base)
            n.zfill(fill)
            return n
        else:
            return self.__lshift__(T3Number(other, self.base))

    def __rdiv__(self, other):
        return self.__class__(other, self.base).__div__(self)

    def __div__(self, other):
        if isinstance(other, T3Number):
            base, fill, cls = self._maxfill(other)
            n = cls(self._int // other._int, base)
            n.zfill(fill)
            return n
        else:
            return self.__div__(T3Number(other, self.base))

    def __ror__(self, other):
        return self.__class__(other, self.base).__or__(self)

    def __or__(self, other):
        if isinstance(other, T3Number):
            base, fill, cls = self._maxfill(other)
            n = cls(self._int | other._int, base)
            n.zfill(fill)
            return n
        else:
            return self.__or__(T3Number(other, self.base))

    def __rand__(self, other):
        return self.__class__(other, self.base).__and__(self)

    def __and__(self, other):
        if isinstance(other, T3Number):
            base, fill, cls = self._maxfill(other)
            n = cls(self._int & other._int, base)
            n.zfill(fill)
            return n
        else:
            return self.__and__(T3Number(other, self.base))

    def __rxor__(self, other):
        return self.__class__(other, self.base).__xor__(self)

    def __xor__(self, other):
        if isinstance(other, T3Number):
            base, fill, cls = self._maxfill(other)
            n = cls(self._int ^ other._int, base)
            n.zfill(fill)
            return n
        else:
            return self.__xor__(T3Number(other, self.base))

    def __eq__ (self, other):
        try:
            if isinstance(other, T3Number):
                return self._int == other._int
            elif isinstance(other, self._convertible_types):
                return T3Number(other, self.base).__eq__(self)
            return False
        except ValueError:
            return False

    def __ne__ (self, hNbr):
        return not self.__eq__(hNbr)

    def __lt__(self, other):
        if isinstance(other, T3Number):
            return self._int < other._int
        elif isinstance(other, self._convertible_types):
            return self.__lt__(self.__class__(other, self.base))
        return False

    def __gt__(self, other):
        if isinstance(other, T3Number):
            return self._int > other._int
        elif isinstance(other, self._convertible_types):
            return self.__gt__(self.__class__(other, self.base))
        return False

    def __le__(self, other):
        if isinstance(other, T3Number):
            return self._int <= other._int
        elif isinstance(other, self._convertible_types):
            return self.__le__(self.__class__(other, self.base))
        return False


    def __ge__(self, other):
        if isinstance(other, T3Number):
            return self._int >= other._int
        elif isinstance(other, self._convertible_types):
            return self.__ge__(self.__class__(other, self.base))
        return False

    def __invert__(self):
        return self.__class__(
            self.__class__(DIGIT_U[self.base - 1]*len(self._str), self.base)._int - self._int, self.base)

    def __index__(self):
        return self._int

    def __int__(self):
        return self._int

    def __getitem__(self, i):
        s = self._str[i]
        if s:
            return self.__class__(self._str[i], self.base)
        else:
            return T3Number.NULL

    def number(self):
        return self._int

    def digits(self):
        return self._str

    def ascii(self):
        chars = []
        for b in self.bytes():
            if b<0:
                chars.append(chr(b+256))
            else:
                chars.append(chr(b))
        return ''.join(chars)

    def bytes(self):
        _bytes = []
        n = self._int
        while n>0:
            n, r = divmod(n, 256)
            _bytes.append(r if r<0x80 else r - 0x100)
        k = 0
        for c in self._str:
            if c == '0':
                k+=1
            else:
                break
        m, r = divmod(k, int(DIGITS_PER_BYTE[self.base]))
        if m:
            _bytes+=[0]*m
        return array('b', _bytes[::-1])

    def zfill(self, width):
        """
        Pad a numeric string S with zeros on the left, to fill a field of the specified width.
        """
        self._str = self._str.zfill(width)
        return self

    def __iter__(self):
        for c in self._str:
            yield T3Number(c, self.base)

    def find(self, sub, start = 0, end = None):
        if end:
            s = self._str[start:end]
        else:
            s = self._str[start:]
        sub = T3Number(sub, self.base)
        return s.find(sub._str)

    def replace(self, old, new, count = -1):
        o_s = self.__class__(old, self.base)._str
        n_s = self.__class__(new, self.base)._str
        return self.__class__(self._str.replace(old, new, count), self.base)


    def split(self, size = 1):
        chunks = []
        n = len(self)
        i = 0
        while i<n:
            chunks.append(self[i:i+size])
            i+=size
        return chunks

    @classmethod
    def join(cls, args):
        if not args:
            return T3Number.NULL
        numbers = [cls(arg) for arg in args]
        if len(numbers) == 1:
            return numbers[0]
        else:
            S = "".join(N._str for N in numbers)
            return cls(S)


    def _getsubst(this):

        class T3NumberSubst:
            def __init__(self):
                self.digits = None
                self.bits = None

            def __getitem__(self, i):
                if self.digits is not None:
                    self.bits = i
                    return self.__call__
                else:
                    self.digits = i
                    return self

            def __call__(self, value):
                if self.digits is None:
                    if hasattr(value, "__call__"):
                        return value(this)
                    else:
                        return this.__class__(value, this.base)
                else:
                    if isinstance(self.digits, slice):
                        a = self.digits.start
                        b = self.digits.stop
                        s = self.digits.step
                        n0, n1, n2 = this[:a], this[self.digits], this[b:]
                    else:
                        n0, n1, n2 = this[:self.digits], this[self.digits], this[self.digits+1:]

                    if self.bits is not None:
                        v     = T3Number(value, 16).number()
                        B     = this._bits_per_item()
                        b_n1  = T3Number(n1, 2)
                        b_n1.zfill(B)
                        if isinstance(self.bits, slice):
                            a = self.bits.start
                            b = self.bits.stop
                            if a<1 or a>B:
                                raise IndexError("Bit index '%d' used. Bit index must be in 1..%d"%(a, B))
                            if b<1 or b>B:
                                raise IndexError("Bit index '%d' used. Bit index must be in 1..%d"%(b, B))
                            a = B - a
                            b = B - b
                            v = T3Number(v & ((2<<abs(b-a))-1), 2).digits()
                        else:
                            a = self.bits
                            if a<1 or a>B:
                                raise IndexError("Bit index '%d' used. Bit index must be in 1..%d"%(a, B))
                            a = b = B - a
                            v = T3Number(v & 1).digits()
                        s = b_n1._str[:a] + v + b_n1._str[b+1:]
                        return n0 // T3Number(T3Number(s, 2), this.base) // n2
                    else:
                        if hasattr(value, "__call__"):
                            return n0 // value(n1) // n2
                        else:
                            return n0 // this.__class__(value, this.base) // n2
        return T3NumberSubst()


    subst = property(_getsubst, None, None,
                        """
subst[i](value)      -> T3Number
subst[i:j](value)    -> T3Number
subst[i][k](value)   -> T3Number
subst[i][k:m](value) -> T3Number

    subst() sets or resets digits of bits in a T3Number and returns a new T3Number
    where those changes have been applied.

    subst() allows single or double subscripting using either indices or slices to access a
    part of the T3Number which shall be changed, then it replaces this part using the
    value argument.

    The value argument is allowed to be a function of one argument returning a number
    which will then substitute the selected part. The selected part is the value of
    the argument passed to the function.


    Examples:

        >>> N = T3Number("56789", 16)
        >>> N.subst[1](0)               # substitute digit 1 of N with 0
        50789
        >>> N.subst[1:3](0)             # shrinks number
        5089
        >>> N.subst[1][3](0)            # sets bit 3 of digit 1 to 0
        52789
        >>> N.subst[1](lambda s: ~s)    # substitutes first digit by its bitwise inversion
        59789
                        """)

    def __repr__(self):
        try:
            return self.formatter()
        except TypeError:            
            return self.formatter(self)

T3Number.formatter = T3NumberFormatter()

############################  _NullNumber  ################################################

class _NullNumber(T3Number):
    def __init__(self, data = None, base = 2):
        self._str = "0"
        self._int = 0
        self.base = 2

    def __repr__(self):
        return "NULL"

    def __len__(self):
        return 0

    def __mul__(self, other):
        return self

    def __add__(self, other):
        return other

    def __rlshift__(self, other):
        return other

    def __rmod__(self, other):
        return other

    def __rrshift__(self, other):
        return other

    def __radd__(self, other):
        return other

    def __rsub__(self, other):
        return other

    def __rmul__(self, other):
        return self

    def __rfloordiv__(self, other):
        return other

    def __ror__(self, other):
        return other

    def __or__(self, other):
        return other

    def __iter__(self):
        yield self


    def _from_string(self, S, base):
        self._str = "0"
        self._int = 0

    def _from_int(self, S, base):
        self._str = "0"
        self._int = 0

    def __eq__(self, other):
        if isinstance(other, _NullNumber):
            return True
        else:
            return False

    def __ne__(self, other):
        return not self.__eq__(other)


T3Number.NULL = NULL = _NullNumber(0, 2)

############################  Bin  ################################################

class Bin(T3Number):
    def __init__(self, data, base = 2):
        super(Bin, self).__init__(data, 2)

    def bytes(self):
        _bytes = []
        n = len(self)
        i = n%8
        if i:
            r = self[0:i].number()
            _bytes.append(r if r<0x80 else r - 0x100)
        while i<n:
            r = self[i:i+8].number()
            _bytes.append(r if r<0x80 else r - 0x100)
            i+=8
        return array('b', _bytes)

############################  Hex  ################################################

class Hex(T3Number):
    def __init__(self, data, base = 16, leftpad = False):
        if isinstance(data, T3Value):
            data = data.get_value()
        if isinstance(data, Bcd):
            data = data.digits()
        elif isinstance(data, T3Number):
            leftpad = True
        super(Hex, self).__init__(data, 16)
        if len(self._str) & 1 == 1:
            if leftpad:
                self._str = "0"+self._str
            else:
                raise ValueError("Hex object was constructed with an odd number of digits: '%s'. An even number was expected"%data)

    def _from_integer(self, n, base):
        super(Hex, self)._from_integer(n, base)
        if len(self._str) & 1 == 1:
            self._str = "0" + self._str

    def modexp(self, x, m):
        expm = []
        for s in x, m:
            if isinstance(s, T3Number):
                expm.append(x._int)
            elif isinstance(s, int):
                expm.append(s)
            else:
                expm.append(T3Number(s)._int)
        return Hex(pow(self._int, expm[0], expm[1]))

    def bytes(self):
        _bytes = []
        for b in self:
            r = b.number()
            _bytes.append(r if r<0x80 else r - 0x100)
        return array('b', _bytes)

    def _bits_per_item(self):
        return 8

    def __len__(self):
        return len(self._str)//2

    def __iter__(self):
        i = 0
        while i<len(self._str):
            yield Hex(self._str[i:i+2])
            i+=2

    def __getitem__(self, i):
        if isinstance(i, slice):
            i = slice(2*i.start if i.start is not None else i.start,
                      2*i.stop if i.stop is not None else i.stop,
                      i.step)
            s = self._str[i]
        elif i>=len(self._str)/2:
            raise IndexError("index out of range")
        else:
            s = self._str[slice(i*2, i*2+2 if i!=-1 else None, 1)]
        if s:
            return self.__class__(s, self.base)
        else:
            return T3Number.NULL

############################  Binary Coded Digits (Bcd) ###################################

class Bcd(T3Number):
    def __init__(self, data, base = 10):
        if isinstance(data, Hex):
            data = data.digits()
        super(Bcd, self).__init__(data, 10)
        if len(self._str) & 1 == 1:
            self.zfill(len(self._str)+1)

    def _num_prefix(self):
        return "n'"

    def _from_t3number(self, N, base):
        if N.base == 10:
            self._int = N._int
            self._str = N._str
        else:
            if N.base == 16 and N._str.isdigit():
                bcd = Bcd(N._str)
            else:
                bcd = Bcd(N._int)
            self._str = bcd._str
            self._int = bcd._int

    def bytes(self):
        _bytes = []
        i = 0
        while i<len(self._str):
            d1 = int(self._str[i])
            d2 = int(self._str[i+1])
            n = (d1<<4) + d2
            _bytes.append(n if n<0x80 else n - 0x100)
            i+=2
        return array('b', _bytes)

    def _from_array(self, a, base):
        if a.typecode == 'b':
            bytes = [(x+256 if x<0 else x) for x in a]
        elif a.typecode == 'B':
            bytes = a.tolist()
        else:
            raise TypeError("invalid typecode '%s' of array. Typecode must be either 'b' or 'B'"%a.typecode)
        S = []
        for i, b in enumerate(bytes):
            d1 = ((b&0xF0)>>4)
            d2 = (b&0x0F)
            if d1>9:
                raise ValueError("Number is not BCD. Digit '%X' found in byte %d"%(d1, i+1))
            if d2>9:
                raise ValueError("Number is not BCD. Digit '%X' found in byte %d"%(d2, i+1))
            S.append(str(d1))
            S.append(str(d2))
        self._str = ''.join(S)
        self._int = int(self._str)


############################  test functions ##########################################

def test_to_int():
    b1 = T3Number("0101", 2)
    assert int(b1) == 5
    b2 = T3Number("0101", 10)
    assert int(b2) == 101   
    b3 = T3Number("0101", 16)
    assert int(b3) == 257

def test_simple_arith():
    b1 = T3Number("0101", 2)
    b2 = T3Number("0010", 2)
    b3 = T3Number("0001", 2)
    assert b1 + b2 == b2 + b1 == 7
    assert b1 * b2 == b2 * b1 == 10
    assert b1 ^ b3 == b3 ^ b1 == 4
    assert b1 - b3 == 4
    assert b1 << 4 == 80
    assert b1 >> 4 == 0

def test_comp_op():
    b1 = T3Number("00000000", 2)
    b2 = T3Number("01", 16)
    b3 = T3Number("01", 10)
    assert b2>b1
    assert b1<b2
    assert b2==b3
    assert b3==b2
    assert b1!=b2
    assert b2!=b1
    assert b1 == 0
    assert 0 == b1
    assert b1 == "00"
    assert "00" == b1
    assert Bin("1100") == Bin("001100")
    assert Bin("1100").digits() != Bin("001100").digits()
    assert list(Bin("1100")) != list(Bin("001100"))

def test_null():
    assert NULL == NULL
    assert T3Number.NULL is NULL
    assert NULL != '00'
    assert NULL[0]   == NULL
    assert NULL[1:3] == NULL
    assert NULL+3 == 3
    assert 3+NULL+3 == 6
    assert 3*NULL == NULL
    assert 3 == 3+NULL
    assert NULL*16 == NULL
    assert NULL*2 == NULL
    assert 1+NULL == 1
    assert NULL<<4 == NULL
    assert NULL>>4 == NULL
    assert int(NULL) == 0
    assert list(NULL) == [NULL]
    assert NULL.digits() == "0"
    assert NULL.bytes()  == array('b')
    assert int(NULL) == 0
    assert NULL // NULL == NULL
    assert NULL // Hex(0x78) == Hex(0x78)
    assert Hex(0x78) // NULL == Hex(0x78)
    assert NULL // Hex(0x78) // NULL  == Hex(0x78)
    assert len(NULL*16) == 0
    assert list(NULL*16) == [NULL]
    assert NULL<<3 == NULL
    assert 3<<NULL == 3

def test_subst():
    b4 = T3Number("00000000", 2)
    assert b4.subst[1](1) == Bin("01000000")
    assert b4.subst[1](1) != Bin("01000001")
    N = T3Number("56789", 16)
    assert N.subst[1](0) == "50789"
    assert N.subst[1:3](0) == "5089", N.subst[1:3](0)
    assert N.subst[1][1](1) == "57789", N.subst[1][1](1)
    assert N.subst[1][2](0) == "54789", N.subst[1][2](0)
    assert N.subst[1][3](0) == "52789", N.subst[1][3](0)
    assert N.subst[1][4](1) == "5E789", N.subst[1][4](1)

    try:
        N.subst[1][0](1)
        assert False, "IndexError exception not raised"
    except IndexError:
        pass
    try:
        N.subst[1][5](1)
        assert False, "IndexError exception not raised"
    except IndexError:
        pass

    N = T3Number("56789", 10)
    assert N.subst[1](0) == "50789"
    assert N.subst[1:3](0) == "5089", N.subst[1:3](0)
    assert N.subst[1][1](1) == "57789", N.subst[1][1](1)
    assert N.subst[1][2](0) == "54789", N.subst[1][2](0)
    assert N.subst[1][3](0) == "52789", N.subst[1][3](0)

    try:
        assert N.subst[1][4](1) == "5E789", N.subst[1][4](1)
        assert False, "IndexError exception not raised"
    except IndexError:
        pass

def test_bcd():
    d = Bcd("00 11 98 15 42 15 52 42 54")
    assert d == Bcd(d.bytes())
    assert d.bytes()  == Bcd(d.bytes()).bytes()
    assert d.digits() == Bcd(d.bytes()).digits()

    d.zfill(19)
    assert str(Bcd(d)) == "n'00 00 11 98 15 42 15 52 42 54"

def test_bin_hex():
    assert Bin(~Hex(0xAF)) & Bin(0xAF) == Bin(0x00)
    assert Bin(~Hex(0xAF)) & Bin(0xAF) == Bin(0x00)
    assert Bin(Hex(Bin('000000000000000000000000'))) == '000000000000000000000000'
    assert Hex(Bin(Hex('00 00 00'))).digits() == '000000'
    assert Bin(T3Number(67, 16)) == '1000011'

def test_tabular_formatting():
    h = Hex("A60289"*29)
    #print h
    h.formatter = T3NumberFormatter(tabular = True)
    assert str(h) == '''    A6 02 89 A6 02 89 A6 02 89 A6 02 89 A6 02 89 A6
    02 89 A6 02 89 A6 02 89 A6 02 89 A6 02 89 A6 02
    89 A6 02 89 A6 02 89 A6 02 89 A6 02 89 A6 02 89
    A6 02 89 A6 02 89 A6 02 89 A6 02 89 A6 02 89 A6
    02 89 A6 02 89 A6 02 89 A6 02 89 A6 02 89 A6 02
    89 A6 02 89 A6 02 89'''

def test_simple_formatting():
    assert str(T3Number("233335334", 6)) == "6'233335334"
    assert str(Bin.join(['110010', 0x6627, T3Number(67, 16)])) == "1100 10110011 00010011 11000011 (h'0C B3 13 C3)"
    assert str(Hex("A9 78")) == "A9 78"

def test_hashing():
    b1 = T3Number("0101", 2)
    b2 = T3Number("0010", 2)    
    d = {b1: "b1", b2: "b2"}
    assert d[2] == "b2"
    assert d[Hex(5)] == "b1"


def test_length():
    b = T3Number("00000000", 2)
    assert len(b) == 8
    b = Bin("00000000")
    assert len(b) == 8    
    h = Hex("0000")
    assert len(h) == 2
    b = Bcd("0000")
    assert len(b) == 4
    try:
        h = Hex("000")
    except ValueError:
        pass
    else:
        assert False, "ValueError not raised"

def test_join():
    assert Hex.join(['72', 0x6627, T3Number(67, 10)]) == '72 66 27 43'
    assert Bin.join(['110010', 0x6627, T3Number(67, 16)]) == '1100 10110011 00010011 11000011'

def test_iter():
    assert list(T3Number("89AF", 16)) == [0x8, 0x9, 0xA, 0xF]
    assert tuple(T3Number("89AF", 16)) == (0x8, 0x9, 0xA, 0xF)    
    assert list(Hex("89AF")) == [0x89, 0xAF]
    assert tuple(Hex("89AF")) == (0x89, 0xAF)

def test_subscript():
    assert T3Number("80 12 34 56", 16)[3]  == 2
    assert Hex("80 12 34 56")[3]  == 0x56
    assert Hex("80 12 34 56")[-1] == 0x56
    try:
        assert Hex("80 01 02 03")[4]  == NULL
    except IndexError:
        pass
    else:
        assert False, "IndexError not raised"

def test_character_conversion():
    assert Hex("88 {\t}") == "88 09"
    assert Hex("{C1i%$} 88 { }{} AF {+?} ") == "43 31 69 25 24 88 20 AF 2B 3F"    
    assert Hex("88 { }") == "88 20"    
    assert Hex("88 {88}") == "88 38 38"    

def test_negation():
    assert Hex(78)-Hex(28) == Hex(50)    
    assert Hex(0)-Hex(28) == Hex(0)    
    try:
        -Hex(78)
    except TypeError:
        pass
    else:
        assert False, "TypeError not raised"
    try:
        Hex(-78)
    except TypeError:
        pass
    else:
        assert False, "TypeError not raised"


if __name__ == '__main__':
    test_to_int()
    test_simple_arith()
    test_comp_op()
    test_null()
    test_subst()
    test_bcd()
    test_tabular_formatting()
    test_hashing()
    test_bin_hex()
    test_negation()
    test_length()
    test_join()
    test_simple_formatting()
    test_iter()
    test_subscript()
    test_character_conversion()


    print Hex("{\{\}} 89")


