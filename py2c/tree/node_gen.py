"""Autogenerate Python files based on a `.tree` definition file.

This module generates the Python files from the custom domain-specific-language
used to declare the nodes that we use during the translation. This way of
describing nodes, allows DRY-ness in the same.
"""

import os
import re
import traceback
import collections
from textwrap import dedent

import ply.lex
import ply.yacc

__all__ = ["PREFIX", "remove_comments", "ParserError", "Parser"]

PREFIX = dedent("""
    # -----------------------------------------------------------------------------
    # This file is auto-generated by ``py2c.tree.node_gen``.
    #
    # Instead of modifying this file, modify the relevant "*.tree" file
    # in py2c/tree directory of the source distribution.
    # -----------------------------------------------------------------------------
    # ANY CHANGES YOU MAKE IN THIS FILE DIRECTLY WILL BE LOST.
    # -----------------------------------------------------------------------------

    from . import Node, identifier, fields_decorator  # noqa
""").strip()


# -----------------------------------------------------------------------------
# Exceptions
# -----------------------------------------------------------------------------
class ParserError(Exception):
    """Errors raised by the Parser while Parsing
    """


# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------
def remove_comments(text):
    """Removes all text after a '#' in all lines of the text
    """
    return re.sub(r"(?m)\#.*($|\n)", "", text)


def _prettify_list(li):
    indent = " "*4
    if li == []:
        return "[]"
    else:
        lines = ["["]
        for name, type_, modifier in li:
            lines.append(
                indent*3 + "({!r}, {}, {!r}),".format(name, type_, modifier)
            )
        lines.append(indent*2 + "]")

        return "\n".join(lines)


Definition = collections.namedtuple("Definition", "name parent fields")


# -----------------------------------------------------------------------------
# Parsing of AST nodes declaration
# -----------------------------------------------------------------------------
class Parser(object):
    """Parses the definitions in the definition files
    """

    def __init__(self):
        super(Parser, self).__init__()
        self.tokens = ("INHERIT", "NAME",)
        self.literals = "()[]:*?+,"

        # Tokens for lexer
        self.t_INHERIT = r"inherit"
        self.t_NAME = r"\w+"
        self.t_ignore = " \t"

        self._lexer = ply.lex.lex(module=self, debug=0)
        self._parser = ply.yacc.yacc(
            module=self, start="start", debug=0, write_tables=0
        )

    def t_newline(self, t):
        r"\n"
        t.lexer.lineno += 1

    def t_error(self, t):
        raise ParserError("Unable to generate tokens from: " + repr(t.value))

    def _reset(self):
        self.seen_node_names = set()

    # -------------------------------------------------------------------------
    # API
    # -------------------------------------------------------------------------
    def parse(self, text):
        """Parses the definition text into a data representation of it.
        """
        self._reset()
        text = remove_comments(text)
        return self._parser.parse(text, lexer=self._lexer)

    # -------------------------------------------------------------------------
    # Parsing
    # -------------------------------------------------------------------------
    def p_error(self, t):
        raise ParserError("Unexpected token: " + str(t))

    def p_empty(self, p):
        "empty : "

    def p_start(self, p):
        "start : zero_or_more_declaration"
        p[0] = p[1]

    def p_zero_or_more_declaration(self, p):
        """zero_or_more_declaration : zero_or_more_declaration declaration
                                    | empty
        """
        if len(p) == 2:
            p[0] = ()
        else:
            p[0] = p[1] + (p[2],)

    def p_declaration(self, p):
        "declaration : NAME parent_class_opt colon_fields_opt"
        name, parent, fields = (p[1], p[2], p[3])
        if name in self.seen_node_names:
            raise ParserError(
                "Multiple declarations of name {!r}".format(name)
            )
        self.seen_node_names.add(name)

        if fields != 'inherit':
            # Check for duplicate fields
            seen_fields = []
            duplicated_fields = []
            for field_name, _, _ in fields:
                if field_name in seen_fields:
                    duplicated_fields.append(field_name)
                else:
                    seen_fields.append(field_name)

            if duplicated_fields:
                msg = "Multiple declarations in {!r} of attribute{} {!r}"
                raise ParserError(msg.format(
                    name,
                    "s" if len(duplicated_fields) > 1 else "",
                    ", ".join(duplicated_fields)
                ))
        elif parent is None:
            msg = (
                "Inheriting nodes need parents to inherit from. "
                "See definition of {!r}"
            )
            raise ParserError(msg.format(name))

        p[0] = Definition(name, parent, fields)

    def p_parent_class_opt(self, p):
        """parent_class_opt : '(' NAME ')'
                            | empty
        """
        if len(p) > 2:
            p[0] = p[2]
        else:
            p[0] = None

    def p_colon_fields_opt(self, p):
        """colon_fields_opt : ':' fields
                            | empty
        """
        if len(p) > 2:
            p[0] = p[2]
        else:
            p[0] = []

    def p_fields(self, p):
        """fields : '[' field_list ']'
                  | INHERIT
        """
        if len(p) == 2:
            p[0] = p[1]
        else:
            p[0] = p[2]

    def p_field_list(self, p):
        """field_list : field more_fields_maybe ','
                      | field more_fields_maybe
                      | empty
        """
        if len(p) > 2:
            p[0] = [p[1]] + p[2]
        else:
            p[0] = []

    def p_more_fields_maybe(self, p):
        """more_fields_maybe : more_fields_maybe ',' field
                            | empty
        """
        if len(p) > 2:
            p[0] = p[1] + [p[3]]
        else:
            p[0] = []

    def p_field(self, p):
        "field : NAME modifier NAME"
        p[0] = (p[3], p[1], p[2])

    def p_modifier(self, p):
        """modifier : empty
                    | '?'
                    | '+'
                    | '*'
        """
        if p[1] == "+":
            p[0] = "ONE_OR_MORE"
        elif p[1] == "*":
            p[0] = "ZERO_OR_MORE"
        elif p[1] == "?":
            p[0] = "OPTIONAL"
        else:
            p[0] = "NEEDED"


# -----------------------------------------------------------------------------
# Generation of sources for AST nodes class
# -----------------------------------------------------------------------------
class SourceGenerator(object):
    """Generates the code from the Parser's parsed data
    """

    def __init__(self):
        super(SourceGenerator, self).__init__()

    # -------------------------------------------------------------------------
    # API
    # -------------------------------------------------------------------------
    def generate_class(self, definition):
        """Generates source code for a class from a `Definition`.
        """
        class_declaration = "class {}({}):\n".format(
            definition.name, definition.parent or "object"
        )
        if definition.fields == "inherit":
            field_declaration = "    pass"
        else:
            field_declaration = (
                "    @fields_decorator\n"
                "    def _fields(cls):\n"
                "        return {}"
            ).format(_prettify_list(definition.fields))
        return class_declaration + field_declaration

    def generate_sources(self, data):
        """Generates source code from the data generated by `Parser`
        """
        classes = []
        for node in data:
            classes.append(self.generate_class(node))

        # Join classes and ensure newline at EOF
        return "\n\n\n".join(classes)


# API
def generate(source_dir, output_dir=None, update=False):  # coverage: not missing
    """Generate sources for the Nodes definition files in ``source_dir``
    """
    if output_dir is None:
        output_dir = source_dir

    # A convinience function for printing the notifications
    def report(*args):
        print("[py2c.tree.node_gen]", *args)

    # Discover files
    files_to_convert = [
        fname for fname in os.listdir(os.path.realpath(source_dir))
        if fname.endswith(".tree")
    ]

    # Writing the node-declaration files
    parser = Parser()
    src_gen = SourceGenerator()

    for fname in files_to_convert:
        infile_name = os.path.join(source_dir, fname)
        outfile_name = os.path.join(output_dir, fname[:-5] + ".py")
        if os.path.exists(outfile_name) and not update:
            continue

        with open(infile_name, "rt") as infile:
            text = infile.read()

        try:
            report("[Py2C] Loading '{}'".format(infile_name))
            sources = src_gen.generate_sources(parser.parse(text))
        except Exception:
            raise Exception(
                "Could not auto-generate sources for '{}'".format(infile_name)
            )
        else:
            report("[Py2C] Writing '{}'".format(outfile_name))
            with open(outfile_name, "w+t") as outfile:
                outfile.write(PREFIX)
                outfile.write("\n\n\n")
                outfile.write(sources)
                outfile.write("\n")

if __name__ == '__main__':
    generate("", "", True)
