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

    query1 = {"status.label":"Active", "observedProperty": param, "_limit": 5000}

    response = requests.get(baseURL+stationsURL, params=query1)
    if response.status_code == 200:
        stationsData = getStationsInfo(response)
    else:
        raise Exception("API error {0}".format(response.status_code))

    return stationsData

def analyseStationsData(stationsWithLevelAndFlow):

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
        
    joinedLevelAndFlowData['name'] = np.where(joinedLevelAndFlowData.waterLevel, joinedLevelAndFlowData.name_x, joinedLevelAndFlowData.name_y)
    joinedLevelAndFlowData['river'] = np.where(joinedLevelAndFlowData.waterLevel, joinedLevelAndFlowData.river_x, joinedLevelAndFlowData.river_y)
    joinedLevelAndFlowData['lat'] = np.where(joinedLevelAndFlowData.waterLevel, joinedLevelAndFlowData.lat_x, joinedLevelAndFlowData.lat_y)
    joinedLevelAndFlowData['long'] = np.where(joinedLevelAndFlowData.waterLevel, joinedLevelAndFlowData.long_x, joinedLevelAndFlowData.long_y)
    
    return joinedLevelAndFlowData[["ref", "name", "river", "waterLevel", "waterFlow", "lat", "long"]]

def categoriseLevelAndFlowData(cleanedLevelAndFlowData, stationsWithMismatchedCoords):

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
