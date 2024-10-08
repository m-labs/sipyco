# Taken from https://github.com/GrahamDumpleton/wrapt/blob/develop/src/wrapt/arguments.py
# Copyright (c) 2013-2023, Graham Dumpleton
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
#
# * Redistributions of source code must retain the above copyright notice, this
#   list of conditions and the following disclaimer.
#
# * Redistributions in binary form must reproduce the above copyright notice,
#   this list of conditions and the following disclaimer in the documentation
#   and/or other materials provided with the distribution.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
# AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
# IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE
# ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE
# LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR
# CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF
# SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS
# INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN
# CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE)
# ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
# POSSIBILITY OF SUCH DAMAGE.

# The inspect.formatargspec() function was dropped in Python 3.11 but we need
# need it for when constructing signature changing decorators based on result of
# inspect.getargspec() or inspect.getfullargspec(). The code here implements
# inspect.formatargspec() base on Parameter and Signature from inspect module,
# which were added in Python 3.6. Thanks to Cyril Jouve for the implementation.

try:
    from inspect import Parameter, Signature
except ImportError:
    from inspect import formatargspec
else:
    def formatargspec(args, varargs=None, varkw=None, defaults=None,
                      kwonlyargs=(), kwonlydefaults={}, annotations={}):
        if kwonlydefaults is None:
            kwonlydefaults = {}
        ndefaults = len(defaults) if defaults else 0
        parameters = [
            Parameter(
                arg,
                Parameter.POSITIONAL_OR_KEYWORD,
                default=defaults[i] if i >= 0 else Parameter.empty,
                annotation=annotations.get(arg, Parameter.empty),
            ) for i, arg in enumerate(args, ndefaults - len(args))
        ]
        if varargs:
            parameters.append(Parameter(varargs, Parameter.VAR_POSITIONAL))
        parameters.extend(
            Parameter(
                kwonlyarg,
                Parameter.KEYWORD_ONLY,
                default=kwonlydefaults.get(kwonlyarg, Parameter.empty),
                annotation=annotations.get(kwonlyarg, Parameter.empty),
            ) for kwonlyarg in kwonlyargs
        )
        if varkw:
            parameters.append(Parameter(varkw, Parameter.VAR_KEYWORD))
        return_annotation = annotations.get('return', Signature.empty)
        return str(Signature(parameters, return_annotation=return_annotation))

