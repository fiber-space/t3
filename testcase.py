# ======================================================================
#
# Copyright (C) 2016 Kay Schluehr (kay@fiber-space.de)
#
# t3testcase.py, v B.0 2016/03/03
#
# ======================================================================

__all__ = ["T3TestCase", "ExpectFailure"]

import abc
import sys
import os
import traceback
import time
from t3.pattern import MatchingFailure

class ExpectFailure(Exception): pass

class T3TestCase(object):
    def __enter__(self):
        settings["testcnt"]+=1
        return self

    def __exit__(self, typ, value, tb):
        if typ:
            if typ in (AssertionError, MatchingFailure, ExpectFailure):
                settings["failcnt"]+=1
                self._status = "FAIL"
                sys.stderr.write("\n<< TEST FAILED >>\n")
            else:
                settings["errcnt"]+=1
                self._status = "ERROR"
            traceback.print_exc()
            return True


