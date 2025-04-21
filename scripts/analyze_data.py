#!/bin/env python

import numpy
import scipy.stats

def fracfact(s):
    # Get the unique list of sorted factors
    factors = set(s) & set('abcdefghijklmnopqrstuvwxyz')
    factors = sorted(factors)
    k = len(factors)

    # Create a dictionary of the pattern for each factor
    d = {"I":numpy.ones(2**k, dtype=numpy.int32)}
    for (i,f) in enumerate(factors):
        d[f] = numpy.array([{False:-1, True:1}[x] for x in (numpy.arange(2**k) & 2**(k-i-1) != 0)])

    # Split the string into each factor's terms
    terms = s.split()

    L = []
    for t in terms:
        v = numpy.copy(d["I"])
        for f in set(t):
            v *= d[f]
        L.append(v)

    M = numpy.matrix(L).transpose()

    return M


def ReshapeData(Data, Trials=1):
    shape = numpy.shape(Data)
    D = numpy.reshape(Data, (shape[0]//Trials, Trials, shape[1]))
    D = numpy.transpose(D, (0,2,1))
    return D


def ReadData(FileName, Trials=1):
    def FormatValue(x):
        try:
            return float(x)
        except:
            return None

    D = numpy.array([[FormatValue(y) for y in x.split(',') if FormatValue(y) != None] for x in open(FileName, 'r').read().splitlines()])

    if Trials != None:
        D = ReshapeData(D, Trials)

    return D


def MatrixToCsv(Data):
    return '\n'.join([','.join([str(x) for x in y]) for y in numpy.array(Data)])


def Analyze2krFactDesign(X, Y, alpha=0.1):
    """Analyze (2^k)r factorial design

    X is a 2-dimensional matrix containing the 2^k factorial design matrix of effects; the dimensions are (experiments, effects).
    The length of experiments is 2^k where k is the number of factors.
    The effects should be generated using fracfact().

    Y is a 3-dimensional matrix containing measured data; the dimensions are (experiments, outputs, replications).
    The length of experiments is 2^k where k is the number of factors.
    The length of replications is r.
    """

    # Get the r and k parameters from the data
    r = int(Y.shape[2])
    k = int(numpy.log2(Y.shape[0]))

    # Calculate the number of data elements from the data
    N = 2**k * r

    # Do error-checking
    if 2**k != Y.shape[0]:
        raise Exception("The number of experiments in Y is not a power of 2.")
    if Y.shape[0] != X.shape[0]:
        raise Exception("The number of experiments in X is not equal to the number of experiments in Y.")

    # Calculate the mean and standard deviation
    Y_mean = numpy.matrix(numpy.mean(Y, 2))
    #Y_std  = numpy.matrix(numpy.std(Y, 2))

    # Calculate the effects and errors
    effects = (Y_mean.transpose() * X / X.shape[0]).transpose()
    SSterms = N * numpy.power(effects, 2)
    SSY = numpy.matrix(numpy.sum(numpy.sum(numpy.power(Y, 2), 2), 0))
    SS0 = numpy.matrix(N * numpy.power(numpy.mean(numpy.mean(Y,2), 0), 2))
    SST = SSY - SS0
    SSE = SST - numpy.sum(SSterms, 0)

    # Calculate the variation
    variation = numpy.divide(SSterms, SST.repeat(SSterms.shape[0], 0))

    # Calculate the standard deviation of errors and effects
    se = numpy.sqrt(numpy.divide(SSE, (2**k * (r - 1))))
    sq = numpy.divide(se, numpy.sqrt(2**k * r))

    # Calculate the confidence intervals
    ci_pm = scipy.stats.t.ppf((1.0-alpha/2.0), 2**k*(r-1)) * sq
    CI = numpy.array([numpy.array(effects-ci_pm), numpy.array(effects+ci_pm)]).transpose(1,2,0)
    CI_zero_included = numpy.int32(numpy.multiply(CI[:,:,0] <= 0, 0 <= CI[:,:,1]))

    # Return the results
    return {"r":         r,
            "k":         k,
            "Y_mean":    Y_mean,
            "effects":   effects,
            "SSterms":   SSterms,
            "SSY":       SSY,
            "SS0":       SS0,
            "SST":       SST,
            "SSE":       SSE,
            "variation": variation,
            "se":        se,
            "sq":        sq,
            "CI":        CI,
            "CI_zero_included": CI_zero_included}


def SampleData(n):
    if n == 1:
        X = fracfact('a b ab')
        Y = numpy.array([[[41.16, 39.02, 42.56],
                          [53.50, 55.50, 50.50],
                          [65.17, 69.25, 64.23],
                          [50.08, 48.98, 47.10]],
                         [[1.05, 0.97, 1.10],
                          [1.50, 1.45, 1.54],
                          [1.75, 1.80, 1.73],
                          [1.25, 1.28, 1.22]]])
        Y = Y.transpose(1, 0, 2)
    elif n == 2:
        X = fracfact('a')
        Y = numpy.array(
            [[1.05, 100.2, 45.3, 14.2],
             [0.97, 98.8, 42.5, 15.0],
             [1.10, 99.4, 43.3, 14.5],
             [1.50, 94.3, 40.2, 18.0],
             [1.45, 92.0, 38.7, 18.2],
             [1.54, 91.8, 40.1, 17.9]])
        Y = ReshapeData(Y, 3)
    elif n == 3:
        X = fracfact('a b c d ab ac ad bc bd cd abc abd acd bcd abcd')
        Y = ReadData("perftest.data", Trials=5)

    return (X,Y)


if __name__ == "__main__":
    X = fracfact('I a b c d ab ac ad bc bd cd abc abd acd bcd abcd')
    Y = ReadData("perftest.data.2", Trials=5)

    results = Analyze2krFactDesign(X, Y, alpha=0.1)
    print numpy.float32(results["variation"] * 100)
    print results["CI_zero_included"]
    print "\nX"
    print MatrixToCsv(X)
    print "\nY_mean"
    print MatrixToCsv(results["Y_mean"])
    print "\neffects"
    print MatrixToCsv(results["effects"])
    print "\nvariation"
    print MatrixToCsv(results["variation"])
    print "\nsq"
    print MatrixToCsv(results["sq"])
