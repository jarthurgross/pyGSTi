#*****************************************************************
#    pyGSTi 0.9:  Copyright 2015 Sandia Corporation              
#    This Software is released under the GPL license detailed    
#    in the file "license.txt" in the top-level pyGSTi directory 
#*****************************************************************
"""
Routines for converting python objects to HTML.  Parallel rountines as
LatexUtil has for latex conversion.
"""

import numpy as _np
import cmath
from .. import objects as _objs


def html(x, brackets=False):
    """
    Convert a numpy array, number, or string to html.

    Parameters
    ----------
    x : anything
        Value to convert into HTML.
        
    brackets : bool, optional
        Whether to include brackets in the output for array-type variables.

    Returns
    -------
    string
        html string for x.
    """
    if isinstance(x,_np.ndarray) or \
       isinstance(x,_objs.Gate) or \
       isinstance(x,_objs.SPAMVec):
        d = 0
        for l in x.shape:
            if l > 1: d += 1
        x = _np.squeeze(x)
        if d == 0: return html_value(x)
        if d == 1: return html_vector(x, brackets=brackets)
        if d == 2: return html_matrix(x, brackets=brackets)
        raise ValueError("I don't know how to render a rank %d numpy array as html" % d)
    elif type(x) in (float,int,complex,_np.float64,_np.int64):
        return html_value(x)
    elif type(x) in (list,tuple):
        return html_list(x)
    elif type(x) == str:
        return html_escaped(x)
    else:
        print "Warning: %s not specifically converted to html" % str(type(x))
        return str(x)


def html_list(l, brackets=False):
    """
    Convert a list to html.

    Parameters
    ----------
    l : list
        list to convert into HTML.
        
    brackets : bool, optional
        Whether to include brackets in the output html.

    Returns
    -------
    string
        html string for l.
    """

    lines = [ ]
    for el in l:
        lines.append( html(el, brackets) )
    return '<div class=math><table cellpadding="0" cellspacing="0" class=matrixbrak> <tr><td>' \
        + '<table cellpadding="0" cellspacing="0" class="matrix"><tr><td>' \
        + "</td></t><tr><td>".join(lines) + "</td></tr></table></td>" + '</tr></table></div>\n'


def html_vector(v, brackets=False):
    """
    Convert a 1D numpy array to html.

    Parameters
    ----------
    v : numpy array
        1D array to convert into HTML.
        
    brackets : bool, optional
        Whether to include brackets in the output html.

    Returns
    -------
    string
        html string for v.
    """

    ROUND = 4
    lines = [ ]
    for el in v:
        lines.append( html_value(el, ROUND) )
    if brackets:
        return '<div class=math><table cellpadding="0" cellspacing="0" class=matrixbrak> <tr><td class="lbrak">&nbsp;</td><td>' \
               + '<table cellpadding="0" cellspacing="0" class="matrix"><tr><td>' + "</td></t><tr><td>".join(lines) + "</td></tr></table></td>" \
               + '<td class="rbrak">&nbsp;</td></tr></table></div>\n'
    else:
        return '<div class=math><table cellpadding="0" cellspacing="0" class=matrixbrak> <tr><td>' \
               + '<table cellpadding="0" cellspacing="0" class="matrix"><tr><td>' + "</td></t><tr><td>".join(lines) + "</td></tr></table></td>" \
               + '</tr></table></div>\n'


def html_matrix(m, fontsize=None, brackets=False):
    """
    Convert a 2D numpy array to html.

    Parameters
    ----------
    m : numpy array
        2D array to convert into HTML.

    fontsize : int, optional
        If not None, the fontsize.
        
    brackets : bool, optional
        Whether to include brackets in the output html.

    Returns
    -------
    string
        html string for m.
    """
    ROUND = 4
    lines = [ ]; prefix = ""
    if fontsize is not None:
        prefix += "" #unsupported currently

    for r in range(m.shape[0]):
        lines.append( "<tr><td>" + " </td><td> ".join( [html_value(el,ROUND) for el in m[r,:] ] ) + "</td></tr>" )

    if brackets:
        return '<div class=math><table cellpadding="0" cellspacing="0" class=matrixbrak> <tr><td class="lbrak">&nbsp;</td><td>' \
               + '<table cellpadding="0" cellspacing="0" class="matrix">' + "\n".join(lines) + "</table></td>" \
               + '<td class="rbrak">&nbsp;</td></tr></table></div>\n'
    else:
        return '<div class=math><table cellpadding="0" cellspacing="0" class=matrixbrak> <tr><td>' \
               + '<table cellpadding="0" cellspacing="0" class="matrix">' + "\n".join(lines) + "</table></td>" \
               + '</tr></table></div>\n'


def html_value(el,ROUND=6,complexAsPolar=True):
    """
    Convert a floating point or complex value to html.

    Parameters
    ----------
    el : float or complex 
        Value to convert into HTML.

    ROUND : int, optional
        Precision with which to round el.

    complexAsPolar : bool, optional
        Whether to output complex values in polar form.  If False, usual
        a+ib form is used.

    Returns
    -------
    string
        html string for el.
    """

    # ROUND = digits to round values to
    TOL = 1e-9  #tolerance for printing zero values

    def render(x):
        if abs(x) < 5*10**(-(ROUND+1)):
            s = "%.0e" % x # one significant figure
        elif abs(x) < 1:
            s = "%.*f" % (ROUND,x)
        elif abs(x) <= 10**ROUND:
            s = "%.*f" % (ROUND-int(_np.log10(abs(x))),x)  #round to get ROUND digits when x is < 1
            #str(round(x,ROUND))  #OLD
        else:
            s = "%.0e" % x # one significant figure

        #Fix scientific notition
        p = s.split('e')
        if len(p) == 2: 
            ex = str(int(p[1])) #exponent without extras (e.g. +04 => 4)
            s = p[0] + "&times;10<sup>" + ex + "</sup>"

        #Strip superfluous endings
        if "." in s:
            while s.endswith("0"): s = s[:-1]
            if s.endswith("."): s = s[:-1]
        return s


    if type(el) == str: return el
    if type(el) in (int,_np.int64):
        return "%d" % el
    if el is None or _np.isnan(el): return "--"

    try:
        if abs(el.real) > TOL: 
            if abs(el.imag) > TOL:
                if complexAsPolar:
                    r,phi = cmath.polar(el)
                    ex = ("i%.1f" % phi) if phi >= 0 else ("-i%.1f" % -phi)
                    s = "%se<sup>%s</sup>" % (render(r),ex)
                else:
                    s = "%s%s%si" % (render(el.real),'+' if el.imag > 0 else '-', render(abs(el.imag)))
            else:
                s = "%s" % render(el.real)
        else:
            if abs(el.imag) > TOL:
                s = "%si" % render(el.imag)
            else:
                s = "0"
    except:
        #try:
        #    if abs(el) > TOL: #throw exception if el is not a number
        #        s = "%s" % render(el.real)
        #    else:
        #        s = "0"
        #except:
        s = str(el)

    return s
            

def html_escaped(txt):
    """
    Escape txt so it is html safe.

    Parameters
    ----------
    txt : string
        value to escape

    Returns
    -------
    string 
    """
    return txt
