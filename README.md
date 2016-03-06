# t3
A binary data construction and manipulation toolkit in Python

## Introduction

When a C-struct is a sequence of named fields of fixed sizes which can be constructed and 
deconstructed using type casts from and to arrays of bytes how can we imagine a generalized 
dynamic C-struct analogon with fields of varying sizes, with functional dependencies between 
those fields, which is constructed and deconstructed using parsers and unparsers?

The `t3` library and in particular the `T3Table` type give possible answers to this question. 

### Construcing binary data types

In essence a TLV is a binary data type which is a concatenation of three fields:

    TLV = Tag || Length || Value

If you want to construct one from an array of bytes you need a parser because each of the Tag, Length 
and Value fields can vary in size. So first of all we need three functions to determine the sizes of
each of those fields:

  * tag_size()
  * length_size()
  * value_size()

Additionally we want to keep the Length of a TLV object in synch with its Value when the Value changes.
This doesn't imply we are after mutable TLVs but using one TLV as a *prototype* for another one seems 
like a good idea. So we add another function 

  * update_length()

Now we can use the `T3Table` to construct a TLV object which at the same type serves as a new data type!

    Tlv = T3Table()
    Tlv.add(tag_size, Tag = "00")
    Tlv.add(length_size, Length = T3Binding(update_length, "Value"))
    Tlv.add(value_size,  Value = "00")

That's it. Let's see how our new data structure works

    >>> Tlv                   ## our Tlv object
    Tlv:
      Tag: 00
      $Len: 01
      Value: 00

    >>> tlv = Tlv << "07 03 99 AF 00"   ## read binary data and create new Tlv
    tlv:
        Tag: 07
        $Len: 03
        Value: 99 AF 00

    >>> tlv.Value             ## get Value
    99 AF 00
    >>> tlv.Tag               ## get Tag
    07

    >>> tlv(Value = "AF 00")  ## create a copy with a different Value
    <Tlv>
      Tag: 07
      $Len: 02
      Value: AF 00

    >>> tlv.Value = "AF 00"   ## modify tlv
    >>> tlv
    tlv:
        Tag: 07
        $Len: 03
        Value: AF 00

    >>> Hex(tlv)             ## unparse tlv
    07 02 AF 00

    >>> assert Hex(tlv << Hex(tlv)) == Hex(tlv)    ## this relation between parsed and unparsed 
                                                   ## objects should always be true for T3Tables

### Building variants

Suppose we drop the Tag because our application uses some tag-less LV data. Using a 
T3Table we can just remove one line from our Tlv construction and define a new `Lv` object

    Lv = T3Table()
    Lv.add(length_size, Length = T3Binding(update_length, "Value"))
    Lv.add(value_size,  Value = "00")

Smartcards in the EMV/payment application domain also know so called (D)ata (O)object (L)ists or DOLs, which are 
lists of TL objects

    Tl = T3Table()
    Tl.add(tag_size, Tag = "00")
    Tl.add(length_size, Length = "00")

Since there is no Value to bind we removed the update rule for Length.

In order to express sequences of objects in t3 we construct a DOL using a T3Repeater:

    DOL = TlList = T3Repeater(Tl)

which can be used to parse Tag-Length lists:

    >>> DOL << "9F5B 07 8A 02 9F01 8180"    
    [<Tl>
      Tag: 9F5B
      Len: 07,
    <Tl>
      Tag: 8A
      Len: 02,      
    <Tl>
      Tag: 9F01
      Len: 8180]

For the purpose of symmetry we complete our discussion with a Length-Value list

    LvList = T3Repeater(Lv)

### Data construction vs data hiding

The pattern should now become clear. All those T3Table, T3Repeater, T3Binding, T3Bitmap etc. objects 
can be mashed together to build new objects which are also data types. 

Contrast the data construction approach of t3 with a [Tlv](http://www.openscdp.org/ocf/api/opencard/opt/util/TLV.html) 
implementation in Java which I've chosen, not because there is anything wrong with it, but because it illustrates 
the opposite approach favoring a data-hiding style using APIs. The API looks like an exoskeleton, which needs 
signifikant modification for each of the datatypes we've created using constructors or editing a single line in
the Tlv code.







