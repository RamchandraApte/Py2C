"""Translates Python code into an AST containing type and control-flow information.
"""

#------------------------------------------------------------------------------
# Py2C - A Python to C++ compiler
# Copyright (C) 2014 Pradyun S. Gedam
#------------------------------------------------------------------------------

import ast

from py2c.base_worker import BaseWorker
from py2c.pre_processing import PreProcessingError


#------------------------------------------------------------------------------
# Exceptions
#------------------------------------------------------------------------------
class SourceToASTTranslationError(PreProcessingError):
    """Raised when fatal error(s) occur in the Translation of source-code to AST.
    """

    def __init__(self):
        super().__init__("Couldn't convert source-code to AST.")


#------------------------------------------------------------------------------
# Translator
#------------------------------------------------------------------------------
class SourceToAST(BaseWorker):
    """Translates Python code into Flow Tree
    """

    def work(self, code):
        """Translate the passed code into a valid Python AST, if the code is valid.
        """
        try:
            node = ast.parse(code)
        except Exception as e:
            raise SourceToASTTranslationError() from e
        else:
            return node