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
    if v in (None, T3Number.NULL):
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


if __name__ == '__main__':
    test_tag()
    '''
    # A = Tlv(Tag = 0x89, Value = 0x72872872)
    # print A

    data = Hex("E8 82 01 0A E9 1D C0 01 05 84 02 02 02 83 14 14 14 14 14 14 14 14 14 14 14 14 14 14 14 14 14 14 14 14 14 EA 81 BE 85 57 57 57 57 57 57 57 57 57 57 57 57 57 57 57 57 57 57 57 57 57 57 57 57 57 57 57 57 57 57 57 57 57 57 57 57 57 57 57 57 57 57 57 57 57 57 57 57 57 57 57 57 57 57 57 57 57 57 57 57 57 57 57 57 57 57 57 57 57 57 57 57 57 57 57 57 57 57 57 57 57 57 57 57 57 57 57 57 F1 55 55 55 55 55 55 55 55 55 55 55 55 55 55 55 55 55 55 55 55 55 55 55 55 55 55 55 55 55 55 55 55 55 55 55 55 55 55 55 55 55 55 55 55 55 55 55 55 55 55 55 55 55 55 55 55 55 55 55 55 55 55 55 55 55 55 55 55 55 55 55 55 55 55 55 55 55 55 55 55 55 55 55 55 55 55 91 03 03 03 03 99 07 07 07 07 07 07 07 07 C7 28 28 28 28 28 28 28 28 28 28 28 28 28 28 28 28 28 28 28 28 28 28 28 28 28 28 28 28 28 28 28 28 28 28 28 28 28 28 28 28 28")
    tlv  = Tlv << data
    print tlv


    dol = xDOL << "9F0A 02 9F27 80"
    print dol
    print Hex(Tlv(Tag = 0x62,
        Value = Tlv(Tag = 0x82, Value = '10')  //
                Tlv(Tag = 0x83, Value = '92')  //
                Tlv(Tag = 0xC0, Value = '89')
        ))

    tlv = Tlv(Tag = 0x00, Value = None)
    print tlv
    assert tlv.Len == 0x00, "Tlv.Len = %s. Expected = 00"%tlv.Len

    T_61 = T3Set()
    T_61.add(0x4F, Tlv_4F = Tlv(Tag = 0x4F, Value = "FF"))
    T_61.add(0x50, Tlv_50 = Tlv(Tag = 0x50))
    T_61.add(0x87, Tlv_87 = Tlv(Tag = 0x87))
    T_61.add(0x9F2A, Tlv_9F2A = Tlv(Tag = 0x9F2A))

    T_BF0C = T3Set()
    T_BF0C.add(0x61, Tlv_61 = Tlv(Tag = 0x61, Value = T_61))

    T_A5 = T3Set()
    T_A5.add(0x88, Tlv_88 = Tlv(Tag = 0x88))
    T_A5.add(0x5F2D, Tlv_5F2D = Tlv(Tag = 0x5F2D))
    T_A5.add(0xBF0C, Tlv_BF0C = Tlv(Tag = 0xBF0C, Value = T_BF0C))

    T_6F = T3Set()
    T_6F.add(0x84, Value = Tlv(Tag = 0x84))
    T_6F.add(0xA5, Value = Tlv(Tag = 0xA5, Value = T_A5))

    Tlv_Pse = T3Set()
    Tlv_Pse.add(0x6F, Value = Tlv(Tag = 0x6F, Value = T_6F))
    Tlv_Ppse = T3Set()
    Tlv_Ppse.add(0x6F, Value = Tlv(Tag = 0x6F, Value = T_6F))

    print Tlv_Ppse << "6F 37 84 0E 32 50 41 59 2E 53 59 53 2E 44 44 46 30 31 A5 25 BF 0C 22 61 20 4F 07 A0 00 00 01 11 01 01 50 0E 50 6F 73 74 46 69 6E 61 6E 63 65 20 43 4C 87 01 01 9F 2A 01 82"

    print TlvDict(TlvList << Hex.join(Tlv(Tag = 0x4F, Value = "FF") // Tlv(Tag = 0x4E, Value = "FF")))
    

    print BERTlv << "C0 06 80 01 00 81 01 01"
    print BERTlv << "80 02 00 00"
    print BERTlv << "5F 01 02 00 00"
    print BERTlv << "7F 05 03 80 01 00"
    btlv = BERTlv << "30 08 80 01 00 E1 03 95 01 00"
    print "-"*100
    print btlv
    print btlv.find_tag("95")
    '''
