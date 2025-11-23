import requests
#import json
#import numpy as np
import pandas as pd
import datetime
import warnings

baseURL = "http://environment.data.gov.uk/hydrology"
readingExt = "/data/readings.json"
measuresExt = "/id/measures.json"

def getAvailableMeasures(stationID):
    """
    Query hydrology API for available measurement timeseries of a given station

    Paramter
    --------
    stationID : string
        GUID of station to extract details of

    Raises
    ------
    Error
        If API query is unsuccessful

    Returns
    -------
    measureInfo : DataFrame
        Available measurement timeseries (rows) and metadata (columns)
    """

    queryParams = {"station": stationID}
    response = requests.get(baseURL+measuresExt, params=queryParams)
    if response.status_code == 200:
        measuresInfo = pd.json_normalize(response.json()["items"])
    else:
        raise Exception("API error {0}".format(response.status_code))

    return measuresInfo

def getAvailableMeasuresAcrossStations(stationIDs):
    """
    Detail all available measures for a group of stations

    Parameter
    ---------
    stationIDs : List
        All GUIDs for stations of interest

    Returns
    -------
    DataFrame
        Available measures timeseries in tidy format with period (e.g. 15-min,
         daily) and value (e.g. max, instantaneous) metadata

    See Also
    --------
    getAvailableMeasures : handles API calls
    tabulateAvailableMeasuresStations : converts outputs to more user-friendly format
    """

    availableMeasuresDFs = [getAvailableMeasures(stationID) for stationID in stationIDs]
    availableMeasures = pd.concat(availableMeasuresDFs)

    return availableMeasures[["station.label", "periodName", "valueType", "parameterName"]]

def tabulateAvailableMeasuresStations(availableMeasuresStationsData):
    """
    Converts output of getAvailableMeasuresAcrossStations to non-tidy table

    Parameter
    ---------
    availableMeasuresStationsData : DataFrame
        Output from getAvailableMeasuresAcrossStations
    
    Returns
    -------
    availableMeasuresStationsData : DataFrame
        Pivotted version of input with True presents if a measure timeseries is
         available for a station (row) and measure (column) combo, na if not
    """

    availableMeasuresStationsData["measure"] = availableMeasuresStationsData["periodName"] + " " + availableMeasuresStationsData["valueType"] + " " + availableMeasuresStationsData["parameterName"]
    availableMeasuresStationsData = availableMeasuresStationsData[["station.label", "measure"]]
    availableMeasuresStationsData.loc[:,"present"] = True
    availableMeasuresStationsData = availableMeasuresStationsData.pivot(index="station.label", columns="measure", values="present")

    return availableMeasuresStationsData

def getReadingsData(stationID, prop="waterLevel", period="daily", valueType=pd.NA):
    """
    Query API for last 1000 readings from a single measure timeseries

    Parameters
    ----------
    stationID : string
        GUID for station to get data for
    prop : string
        observedProperty to pass to API call (waterLevel default)
    period : string
        "daily" (default) to query the API for a timeseries reported as such, otherwised
         assumed 15-min
    valueType : string
        valueType to pass to API call, pd.NA (default) to not pass a valueType
    
    Raises
    ------
    Error
        If API call returns status that isn't '200'
    
    Returns
    -------
    measuresData : DataFrame
        API return with call metadata

    See Also
    --------
    cleanMeasuresData : cleaning for max daily timeseries
    """

    readingParams = {"station": stationID, "observedProperty": prop}
    currentDatetime = datetime.datetime.now()

    if period == "daily":
        startDate = currentDatetime - datetime.timedelta(days=1000)
        readingParams["period"] = 86400
    else:
        startDate = currentDatetime - datetime.timedelta(hours=250)
        readingParams["period"] = 900

    readingParams["mineq-date"] = datetime.datetime.strftime(startDate, "%Y-%m-%d")

    if not(pd.isna(valueType)):
        readingParams["valueType"] = valueType

    response = requests.get(baseURL+readingExt, params=readingParams)
    if response.status_code == 200:
        measuresData = pd.json_normalize(response.json()["items"])
    else:
        raise Exception("API error {0}".format(response.status_code))

    measuresData["station"] = stationID
    measuresData["observedProperty"] = prop
    measuresData["period"] = period
    measuresData["valueType"] = valueType

    return measuresData

def cleanMeasuresData(rawMeasuresData):
    """
    Make unique daily max measurement timeseries

    Parameter
    ---------
    rawMeasuresData : DataFrame
        Output from getReadingsData

    Returns
    -------
    DataFrame
        Cleaned version of getReadingsData with max 1 observation per date

    See Also
    --------
    getLocalMaximums : Identifies highest observations (that are local
     maximums) in the timeseries
    """

    dayUIDs = rawMeasuresData.groupby("date").idxmax()["value"]
    dayUIDs = dayUIDs.dropna()
    
    return rawMeasuresData.iloc[dayUIDs,:]

def getLocalMaximums(measuresData, n=5):
    """
    Identify location of highest observations that are local maximums
    
    Parameters
    ----------
    measuresData : DataFrame
        Output from cleanMeasuresData
    n : integer
        Number of locations to identify. 5 (default) identfiies 5 highest
         local maximums

    Returns
    -------
    DataFrame
        Subset of measuresData containing n largest obs

    See Also
    --------
    getDataNearTargetData : extracts detailed data around specified date
    """
    
    measuresData = measuresData.sort_values('date')
    measuresData = measuresData.assign(
        lastValue = lambda df: df.value.shift(1),
        nextValue = lambda df: df.value.shift(-1)
    ).assign(
        localMax = lambda df: (df.value > df.lastValue) & (df.value > df.nextValue)
    )
    maximums = measuresData.query('localMax')
    
    return maximums.nlargest(n, 'value')

def getDataNearTargetDate(stationID, targetDate):
    """
    Query 15-min waterLevel data 5 days either side of given date

    Parameters
    ----------
    stationID : string
        GUID of station for which to query data
    targetDate : string
        Focal date in YYYY-MM-DD format

    Raises
    ------
    Error
        If API query results in status that is not '200'

    Warns
    -----
    Warning
        If query returns no data (series has no readings around focal date)

    Returns
    -------
    levelMeasures : DataFrame
        Result from API call
    
    See Also
    --------
    getDataNearMaximums : runs this function for a list of dates
    """

    targetDatetime = datetime.datetime.strptime(targetDate, "%Y-%m-%d")

    startDate = targetDatetime - datetime.timedelta(days=5)
    startDate = datetime.datetime.strftime(startDate, "%Y-%m-%d")
    endDate = targetDatetime + datetime.timedelta(days=5)
    endDate = datetime.datetime.strftime(endDate, "%Y-%m-%d")

    readingURL = "/data/readings.json"
    readingParams = {"station": stationID, "observedProperty": "waterLevel",
        "mineq-date": startDate, "period": 900, "maxeq-date": endDate} 
    response = requests.get(baseURL+readingURL, params=readingParams)
    if response.status_code == 200:
        levelMeasures = pd.json_normalize(response.json()["items"])
    else:
        raise Exception("API error {0}".format(response.status_code))

    if levelMeasures.shape[0] > 0:
        levelMeasures = levelMeasures.sort_values('dateTime')
    else:
        warnings.warn("No detailed data available around "+targetDate, Warning)

    return levelMeasures

def getDataNearMaximums(maximumObs, stationID):
    """
    Get data 5 days either side of specified dates for a list of dates

    Parameters
    ----------
    maximumObs : DataFrame
        date column specifies target dates
    stationID : string
        GUID of station to get data for

    Returns
    -------
    dataAroundPeaks : DataFrame
        Concated returns from getDataNearTargetDate with peakDate column to
         identfiy focal dates
    
    See Also
    --------
    getDataNearTargetDate : Queries API for waterLevel 5 days either side of
     specified focal date
    """

    dataAroundPeaks = pd.DataFrame()
    for i in range(maximumObs.shape[0]):
        peakLoc = maximumObs.date.iloc[i]
        dataAroundPeak = getDataNearTargetDate(stationID, peakLoc)
        dataAroundPeak = dataAroundPeak.assign(peakDate = peakLoc)
        dataAroundPeak = dataAroundPeak.reset_index()
        dataAroundPeaks = pd.concat([dataAroundPeaks, dataAroundPeak])

    return dataAroundPeaks


if __name__ == "__main__":

    nettlehamID = "a941c6ca-6b2e-45b3-a515-198c39d4ceaa"
    levelMeasures = getReadingsData(nettlehamID)
    measuresUnique = cleanMeasuresData(levelMeasures)

    measuresUnique.plot(x="date", y="value")

    warnings.simplefilter("always")

    peaks = getLocalMaximums(measuresUnique)
    dataNearPeaks = getDataNearMaximums(peaks, nettlehamID)

    valuesAroundPeaks = dataNearPeaks.pivot(columns = 'peakDate', values = 'value')
    valuesAroundPeaks.plot()