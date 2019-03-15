#!/usr/bin/env python
# -*- coding: utf-8 -*-

from itertools import zip_longest
import string
from enum import IntEnum


_horizontal_whitespace = " \t"

_identifier_start = string.ascii_letters + "_$"
_identifier = _identifier_start + string.digits


class TokenType(IntEnum):
	EndOfStream = 1
	Newline     = 2
	Indent      = 3
	Dedent      = 4
	Comment     = 5
	Identifier  = 6
	Integer     = 7
	String      = 8
	Symbol      = 9


class Token:
	def __init__(self, type, value, span=None):
		self.type = type
		self.value = value
		self.span = span

	def __str__(self):
		if self.span is not None:
			begin, end = self.span
			return "<%s: %s, %r (%d:%d, %d:%d)>" % (self.__class__.__name__, self.type.name, self.value, *begin, *end)
		else:
			return "<%s: %s, %r>" % (self.__class__.__name__, self.type.name, self.value)


class LexerError(Exception):
	pass


class LexerState:
	def __init__(self, lexer):
		self.lexer = lexer
		self.ptr = lexer.ptr
		self.line, self.character = lexer.line, lexer.character

	def _apply(self):
		self.lexer.ptr = self.ptr
		self.lexer.line, self.lexer.character = self.line, self.character


class LexerPeeking:
	def __init__(self, lexer):
		self.lexer = lexer
		self.state = lexer.get_state()

	def save(self):
		self.state = self.lexer.get_state()

	def __enter__(self):
		self.save()
		return self

	def __exit__(self, exc_type, exc_value, traceback):
		self.lexer.set_state(self.state)


class Lexer:
	def __init__(self, string):
		self.string = string
		self.length = len(string)
		self.ptr = 0
		self.line, self.character = 1, 0
		self.indentations = []
		self.indentations.append("")

	def _fail(self, message, span):
		begin, end = span
		raise LexerError("%s (%d:%d, %d:%d)" % (message, *begin, *end))

	def _next(self):
		if self.ptr >= self.length:
			raise LexerError("Unexpected end of stream")

		c = self.string[self.ptr]
		self.ptr += 1

		if c == "\n":
			self.line += 1
			self.character = 0
		else:
			self.character += 1

		return c

	def next(self):
		if self.ptr >= self.length:
			span_end = self.line, self.character

			if len(self.indentations) > 1:
				self.indentations.pop()
				return Token(TokenType.Dedent, self.indentations[-1], (span_end, span_end))

			return Token(TokenType.EndOfStream, "", (span_end, span_end))

		c = self.string[self.ptr]

		if self.character == 0:
			with self.peeking() as p:
				span_begin = self.line, self.character
				begin = self.ptr

				empty_line = False

				while True:
					c2 = self._next()
					if not c2.isspace():
						break
					if c2 == "\n":
						empty_line = True
						break

				if empty_line:
					p.save()
					span_end = self.line, self.character
					return Token(TokenType.Newline, self.string[begin:self.ptr], (span_begin, span_end))

			if c not in _horizontal_whitespace:
				if len(self.indentations) > 1:
					self.indentations.pop()
					span_end = self.line, self.character
					return Token(TokenType.Dedent, self.indentations[-1], (span_end, span_end))
			else:
				span_begin = self.line, self.character
				begin = self.ptr
				while self.ptr < self.length:
					if self.string[self.ptr] not in _horizontal_whitespace:
						break
					self._next()
				span_end = self.line, self.character

				if self.string[self.ptr] != "#":
					old_indent = self.indentations[-1]
					new_indent = self.string[begin:self.ptr]

					for i, (old, new) in enumerate(zip_longest(old_indent, new_indent)):
						if old is None:
							self.indentations.append(new_indent)
							return Token(TokenType.Indent, new_indent, (span_begin, span_end))

						if new is None:
							self.indentations.pop()
							return Token(TokenType.Dedent, new_indent, (span_begin, span_end))

						if old != new:
							self._fail("Inconsistent use of tabs and spaces in indentation", (span_begin, span_end))

		while self.ptr < self.length:
			if self.string[self.ptr] not in _horizontal_whitespace:
				break
			self._next()

		c = self.string[self.ptr]

		if c == "#":
			span_begin = self.line, self.character
			begin = self.ptr
			while self.ptr < self.length:
				if self.string[self.ptr] in "\r\n":
					break
				self._next()
			span_end = self.line, self.character
			return Token(TokenType.Comment, self.string[begin:self.ptr], (span_begin, span_end))

		if c.isdigit():
			span_begin = self.line, self.character
			begin = self.ptr
			while self.ptr < self.length:
				if not self.string[self.ptr].isdigit():
					break
				self._next()
			span_end = self.line, self.character
			return Token(TokenType.Integer, self.string[begin:self.ptr], (span_begin, span_end))

		if c in _identifier_start:
			span_begin = self.line, self.character
			begin = self.ptr
			while self.ptr < self.length:
				if self.string[self.ptr] not in _identifier:
					break
				self._next()
			span_end = self.line, self.character
			return Token(TokenType.Identifier, self.string[begin:self.ptr], (span_begin, span_end))

		if c in "\"'":
			span_begin = self.line, self.character
			begin = self.ptr
			quote = self._next()
			while True:
				c = self._next()
				if c == "\\":
					self._next()
					continue
				if c == quote:
					break
				if c == "\n":
					self._fail("Unexpected end of line while scanning string literal", (span_begin, (self.line, self.character)))
			span_end = self.line, self.character
			return Token(TokenType.String, self.string[begin:self.ptr], (span_begin, span_end))

		if self.string[self.ptr] in "\r\n":
			span_begin = self.line, self.character
			begin = self.ptr
			if self._next() == "\r":
				assert self._next() == "\n"
			span_end = self.line, self.character
			return Token(TokenType.Newline, self.string[begin:self.ptr], (span_begin, span_end))

		assert not c.isspace()

		span_begin = self.line, self.character
		c = self._next()
		span_end = self.line, self.character

		return Token(TokenType.Symbol, c, (span_begin, span_end))

	def peek(self, offset=0):
		with self.peeking():
			for _ in range(offset):
				self.next()
			return self.next()

	def peeking(self):
		return LexerPeeking(self)

	def get_state(self):
		return LexerState(self)

	def set_state(self, state):
		assert self == state.lexer
		state._apply()

	def __iter__(self):
		while True:
			token = self.next()
			yield token
			if token.type == TokenType.EndOfStream:
				break
