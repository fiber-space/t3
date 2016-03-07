'''
This module defines a Tlv data structure
'''

import t3
from functools import reduce
from t3 import T3Binding, T3Table, Hex, T3Repeater, T3Number, T3Set, T3Bitset, T3Bitmap, T3Match, T3List
from collections import OrderedDict

##############################  Tlv  ###########################################################

# A Tlv implementation which doesn't distinguish between primitive/constructed Tlvs. For a full
# BER Tlv implementation see below.

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
    if isinstance(tlv.Value, t3.pattern.T3Matcher):
        return tlv.Value
    if tlv.Len[0] & 0x80 == 0x80:
        return int(tlv.Len[1:])
    else:
        return int(tlv.Len)

def update_len(v):
    if v is None or v is T3Number.NULL:
        return 0x00
    k = Hex(len(Hex(v)))
    if k<0x80:
        return k
    return (0x80 + len(k)) // k


class T3Tlv(T3Table): 
    def find_tag(self, tag):
        if Hex(self.Tag) == tag:
            return self
        if isinstance(self.Value, T3List):
            for tlv in self.Value:        
                res = tlv.find_tag(tag)
                if res:
                    return res
Tlv = T3Tlv()
Tlv.__doc__ = """
T(ag) L(ength) V(alue) data structure
"""
Tlv.add(tag_size, Tag = "00")
Tlv.add(len_size, Len = T3Binding(update_len, "Value"))
Tlv.add(value_size, Value = "00")

##############################  Lv  ###########################################################

Lv = T3Table()
Lv.__doc__ = """
L(ength) V(alue) data structure
"""
Lv.add(len_size, Len = T3Binding(update_len, "Value"))
Lv.add(value_size, Value = "00")

##############################  Tl  ###########################################################

Tl = T3Table()
Tl.__doc__ = """
T(ag) L(ength) data structure
"""
Tl.add(tag_size, Tag = "00")
Tl.add(len_size, Len = "00")


##############################  List variants  ################################################

TlvList = T3Repeater(Tlv)
LvList  = T3Repeater(Lv)
TlList  = T3Repeater(Tl)

##############################  BER TLV  ################################################

# We distinguish here between primitive and constructed TLVs and create a recursive 
# pattern

BerClass = T3Bitset(2)
BerClass.set(UniversalClass       = '00')
BerClass.set(ApplicationClass     = '01')
BerClass.set(ContextSpecificClass = '10')
BerClass.set(PrivateClass         = '11')

PC = T3Bitset(1)
PC.set(Primitive   = 0)
PC.set(Constructed = 1)

B1 = T3Bitmap()
B1.add(BerClass, BerClass = 0)
B1.add(PC, PC = 1)
B1.add(5, TagNumber = 0)

B2 = T3Bitmap()
B2.add(1, Next = 0)
B2.add(7, TagNumber = 0)

def long_form(tag, data):
    if tag.Head.TagNumber == 0x1F:
        for k in range(1, len(data)):
            if data[k] & 0x80 != 0x80:
                break
        return k
    else:
        return 0

BerTag = T3Table()
BerTag.add(B1, Head = 0)
BerTag.add(long_form, Tail = 0)

class TlvListMatcher(t3.pattern.T3Matcher):
    def __init__(self, size):
        self.size = size

    def match(self, data, table = None):
        size = self.size
        m = BERTlvList.match(data[:size])
        if m.fail:
            return m
        return T3Match(m.value, data[size:])

def primitive_or_constructed(tlv, data):
    if isinstance(tlv.Value, t3.pattern.T3Matcher):
        return tlv.Value
    if tlv.Len[0] & 0x80 == 0x80:
        size = int(tlv.Len[1:])
    else:
        size = int(tlv.Len)
    if tlv.Tag.Head.PC:
        return TlvListMatcher(size)
    else:
        return size

BERTlv = T3Tlv()
BERTlv.add(BerTag, Tag = "00")
BERTlv.add(len_size, Len = T3Binding(update_len, "Value"))
BERTlv.add(primitive_or_constructed, Value = "00")

BERTlvList = T3Repeater(BERTlv)

###########################################################################################
#
#
#           Variants: TlvList, TlList ( = xDOL ), LvList
#
#
###########################################################################################

TlList = DOL = xDOL = T3Repeater(T3Table().add(tag_size, Tag = "00")
                                          .add(len_size, Len = "00"))
TlvList = T3Repeater(Tlv)
LvList = T3Repeater(Lv)

class TlvDict(OrderedDict):
    def __init__(self, *args, **kwd):
        if args and len(args) == 1:
            if isinstance(args[0], T3Tlv):
                super(TlvDict, self).__init__([(args[0].Tag, args[0])], **kwd)
            else:
                super(TlvDict, self).__init__(**kwd)
                for arg in args[0]:
                    if isinstance(arg, T3Tlv):
                        self.__setitem__(arg.Tag, arg)
                    else:
                        raise TypeError("Tlv object expected. '%s' found"%type(arg))


def parse_with_dol(data, dol):
    data = Hex(data)
    offset = 0
    tlvs = []
    for tl in dol:
        tlvs.append( Tlv(Tag = tl.Tag, Value = data[offset: offset + int(tl.Len)]))
        offset += int(tl.Len)
    return tlvs

######################################  Test #######################################

def test_tag():
    tag = BerTag << "C0"
    assert tag.Head.BerClass == 0x03
    assert tag.Head.TagNumber == 0    
    assert tag.Tail == T3Number.NULL

    tlv = BERTlv << "80 02 00 00"
    assert Hex(tlv.Tag) == 0x80
    assert tlv.Len == 0x02
    assert tlv.Value == "00 00"

    tlv = BERTlv << "7F 05 03 80 01 00"
    assert Hex(tlv.Tag) == 0x7F05
    assert tlv.Len == 0x03
    assert isinstance(tlv.Value, T3List)
    assert tlv.find_tag("80").Value == 0x00

def test_length():    
    tlv = Tlv << "80 00"
    assert tlv.Len == "00"
    tlv = Tlv(Tag = 0x80, Value = T3Number.NULL)
    assert tlv.Len == "00"

    tlv = Tlv(Tag = 0x80, Value = None)
    assert tlv.Len == "00"

    tlv = Tlv << "80 7F "+ 0x7F*"00"
    assert tlv.Len == "7F"
    tlv = Tlv(Tag = 0x80, Value = 0x7F*"00")
    assert tlv.Len == "7F"

    tlv = Tlv << "80 81 80 "+ 0x80*"00"
    assert tlv.Len == "81 80"
    tlv = Tlv(Tag = 0x80, Value = 0x80*"00")
    assert tlv.Len == "81 80"

    tlv = Tlv << "80 82 01 20 "+ 0x120*"00"
    assert tlv.Len == "82 01 20"
    tlv = Tlv(Tag = 0x80, Value = 0x120*"00")
    assert tlv.Len == "82 01 20"

def test_tlv_concatenation():    
    T = Tlv(Tag = 0x82, Value = '10')  // Tlv(Tag = 0x83, Value = '92') // Tlv(Tag = 0xC0, Value = '89')
    assert Hex(T) == "82 01 10 83 01 92 C0 01 89"
    assert Tlv(Tag = 0x62, Value = T).Value == T   
    c = Tlv(Tag = 0x62, Value = T)
    c.Value.pop()
    print Hex(c) == "62 06 82 01 10 83 01 92"


if __name__ == '__main__':
    test_tag()
    test_length()
    test_tlv_concatenation()