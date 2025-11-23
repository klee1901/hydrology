# KL # 24/08/2025
# Initial exploration of hydrology data

import requests
#import json
import numpy as np
import pandas as pd
import geopandas as gpd
from shapely.geometry import Point
from levelAnalysis import (getReadingsData, cleanMeasuresData, getAvailableMeasures,
                            getAvailableMeasuresAcrossStations, tabulateAvailableMeasuresStations,
                            getLocalMaximums, getDataNearMaximums, getDataNearTargetDate)
import datetime # For levelAnalysis functions
import warnings

baseURL = "http://environment.data.gov.uk/hydrology"

def getStationsInfo(JSONresponse):
    """
    Create DataFrame of station metadata given an API response from a query of
     the stations API

    Parameter
    ---------
    JSONresponse : List
        Result of successful API call to the list of monitoring stations API

    Returns
    -------
    DataFrame
        Extracted information from json data with 1 row per station

    See Also
    --------
    queryStationData : Calls stations API for given property 
    """

    stations = JSONresponse.json()["items"]

    allStationInfo = []

    for station in stations:
        
        stationInfo = {
            "name": station["label"],
            "river": [station["riverName"] if "riverName" in station else ""][0],
            "ref": station["stationGuid"],
            "lat": station["lat"],
            "long": station["long"]
            }
        allStationInfo.append(stationInfo)

    return pd.DataFrame(allStationInfo)

def queryStationData(param):
    """
    Extract metadata on stations that measure a particular property

    Parameter
    ---------
    param : string
        observedProperty to pass to API call

    Raises
    ------
    Error
        If API call is unsuccessful

    Returns
    -------
    stationsData : DataFrame
        station metadata extracted by getStationsInfo
    """

    query1 = {"status.label":"Active", "observedProperty": param, "_limit": 5000}

    response = requests.get(baseURL+stationsURL, params=query1)
    if response.status_code == 200:
        stationsData = getStationsInfo(response)
    else:
        raise Exception("API error {0}".format(response.status_code))

    return stationsData

def analyseStationsData(stationsWithLevelAndFlow):
    """
    Display summary stats of stations that have either waterLevel, waterFlow (or
     both) measures

    Parameter
    ---------
    stationsWithLevelAndFlow : DataFrame
        Merged outputs from queryStationData (for 'waterLevel' and 'waterFlow')
         with boolean columns to note present of measurement data for these
         properties

    Returns
    -------
    anyMisaligned : DataFrame
        Subset of stationsWithLevelAndFlow where different metadata has been
         reported when querying flow stations than level stations

    See Also
    --------
    categoriseLevelAndFlowData :  Assigns column (on to cleaned data) that
     captures similar information to this
    """

    # Count stations with only one of desired measures
    nLevelOnly = len(stationsWithLevelAndFlow.query("waterLevel and not(waterFlow)"))
    nFlowOnly = len(stationsWithLevelAndFlow.query("not(waterLevel) and waterFlow"))
    print("{0} stations have no Flow measure, {1} stations have no Level measure".format(nLevelOnly, nFlowOnly))

    # Check data aligns for stations with both measures
    stationsWithBoth = (stationsWithLevelAndFlow.query("waterLevel and waterFlow")
                                    .assign(namesMisaligned = lambda df: df.name_x != df.name_y,
                                            riversMisaligned = lambda df: df.river_x != df.river_y,
                                            latMisaligned = lambda df: df.lat_x != df.lat_y,
                                            longMisaligned = lambda df: df.long_x != df.long_y))
    anyMisaligned = stationsWithBoth.query("namesMisaligned or riversMisaligned or latMisaligned or longMisaligned")
    print("""{0} stations have conflicts: {1} stations have name conflicts,
            {2} stations have river conflicts, {3} stations have lat conflicts,
            {4} stations have long conflicts""".format(len(anyMisaligned),
                sum(stationsWithBoth.namesMisaligned), sum(stationsWithBoth.riversMisaligned),
                sum(stationsWithBoth.latMisaligned), sum(stationsWithBoth.longMisaligned)))
    
    return anyMisaligned

def cleanLevelAndFlowData(joinedLevelAndFlowData):
    """
    Simplify merged data from calling queryStationData for level and flow measures

    Parameter
    ---------
    joinedLevelAndFlowData : DataFrame
        Merged outputs from queryStationData (for 'waterLevel' and 'waterFlow')
         with boolean columns indicating whether station has measure timeseries
         for waterLevel and/or waterFlow

    Returns
    -------
    DataFrame
        stations data with single name, river, lat , long variables
    """
        
    joinedLevelAndFlowData['name'] = np.where(joinedLevelAndFlowData.waterLevel, joinedLevelAndFlowData.name_x, joinedLevelAndFlowData.name_y)
    joinedLevelAndFlowData['river'] = np.where(joinedLevelAndFlowData.waterLevel, joinedLevelAndFlowData.river_x, joinedLevelAndFlowData.river_y)
    joinedLevelAndFlowData['lat'] = np.where(joinedLevelAndFlowData.waterLevel, joinedLevelAndFlowData.lat_x, joinedLevelAndFlowData.lat_y)
    joinedLevelAndFlowData['long'] = np.where(joinedLevelAndFlowData.waterLevel, joinedLevelAndFlowData.long_x, joinedLevelAndFlowData.long_y)
    
    return joinedLevelAndFlowData[["ref", "name", "river", "waterLevel", "waterFlow", "lat", "long"]]

def categoriseLevelAndFlowData(cleanedLevelAndFlowData, stationsWithMismatchedCoords):
    """
    Assign categories to output from cleanLevelAndFlowData depending on whether
     it has a measurement timeseries for 'waterLevel', 'waterFlow', neither, or
     both

    Parameters
    ----------
    cleanedLevelAndFlowData : DataFrame
        List of stations output from cleanLevelAndFlowData
    stationsWithMismatchedCoords : DataFrame
        List of stations output from anyMisaligned

    Returns
    -------
    cleanedLevelAndFlowData : DataFrame
        List of stations with additional 'cat' column
    """

    # Split into 4 categories and plot
    missalignedStations = stationsWithMismatchedCoords[["ref"]].assign(misaligned = True)
    missalignedStations["ref"] = missalignedStations["ref"].astype(str)
    cleanedLevelAndFlowData["ref"] = cleanedLevelAndFlowData["ref"].astype(str)
    cleanedLevelAndFlowData = (pd.merge(cleanedLevelAndFlowData, missalignedStations, how="left", on="ref")
                        .convert_dtypes()
                        .fillna({"misaligned": False}))
    cleanedLevelAndFlowData["cat"] = np.where(cleanedLevelAndFlowData.waterLevel, "Level only", "Flow only")
    cleanedLevelAndFlowData["cat"] = np.where(cleanedLevelAndFlowData.apply(lambda df: df.waterLevel and df.waterFlow, axis=1), "Both", cleanedLevelAndFlowData.cat)
    cleanedLevelAndFlowData["cat"] = np.where(cleanedLevelAndFlowData.misaligned, "Both (non-matching)", cleanedLevelAndFlowData.cat)

    return cleanedLevelAndFlowData

def getNearestStations(stationLocations, target, n=5):
    """
    Return list of n nearest stations to a pair of coordinates (target)

    Parameters
    ----------
    stationLocations : GeoDataFrame
        List of all stations to consider
    target : Point
        Location (in same crs as stationLocations) to search near
    n : integer
        Number of stations to return. 5 (default) returns 5 nearest stations to
         target

    Returns
    -------
    DataFrame
        Subset of stationLocations containing n nearest to target
    """

    stationLocations["distFromTarget"] = stationLocations["geometry"].distance(target)

    return stationLocations.nsmallest(n, "distFromTarget")


stationsURL = "/id/stations.json"

if __name__ == "__main__":

    levelStations = queryStationData("waterLevel")
    flowStations = queryStationData("waterFlow")

    levelStations["ref"] = levelStations["ref"].astype(str)
    flowStations["ref"] = flowStations["ref"].astype(str)
    allStations = (pd.merge(levelStations.assign(waterLevel = True),
                        flowStations.assign(waterFlow = True),#[["ref","waterFlow"]],
                        how="outer", on="ref"))

    allStations = (allStations.convert_dtypes()
                            .fillna({'waterLevel':False,'waterFlow':False}))

    anyMisaligned = analyseStationsData(allStations)
    stationsTidy = cleanLevelAndFlowData(allStations)

    stationsTidy = categoriseLevelAndFlowData(stationsTidy, anyMisaligned)

    # Geostuff
    stationsGeo = gpd.GeoDataFrame(
        stationsTidy,
        geometry = gpd.points_from_xy(stationsTidy.long, stationsTidy.lat),
        crs = "EPSG:4326"
    )
    stationsGeo.explore(column="cat", tooltip = "name", popup = True, tiles = "CartoDB positron")

    localStations = getNearestStations(stationsGeo, Point(-0.586698,53.239504))
    localStations.explore(column="cat", tooltip = "name", popup = True, tiles = "CartoDB positron")

    availableMeasuresLocally = getAvailableMeasuresAcrossStations(localStations.ref)
    availableMeasuresTable = tabulateAvailableMeasuresStations(availableMeasuresLocally)

    availableMeasuresLocally["parameterName"] = "water" + availableMeasuresLocally["parameterName"]
    availableMeasuresLocally = pd.merge(availableMeasuresLocally, localStations[["ref","name"]],
                                        left_on = "station.label", right_on="name")

    latestDataDFs = availableMeasuresLocally.apply(lambda x: getReadingsData(x.ref, x.parameterName, x.periodName, x.valueType), axis=1)
    latestData = pd.concat(list(latestDataDFs))

    localLevelStationIDs = localStations.query("waterLevel").ref

    # Enable warnings to be raised when querying 15-min data
    warnings.simplefilter("always")

    for stationID in localLevelStationIDs:

        levelMeasures = getReadingsData(localStations.iloc[stationID, 0])
        measuresUnique = cleanMeasuresData(levelMeasures)
        measuresUnique.plot(
            x="date", y="value", title=localStations.iloc[stationID, 1]
        )

        peaks = getLocalMaximums(measuresUnique)
        dataNearPeaks = getDataNearMaximums(peaks, localStations.iloc[stationID, 0])

        valuesAroundPeaks = dataNearPeaks.pivot(columns = 'peakDate', values = 'value')
        valuesAroundPeaks.plot()
