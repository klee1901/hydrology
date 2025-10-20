# KL # 24/08/2025
# Initial exploration of hydrology data

import requests
import json
import numpy as np
import pandas as pd
import geopandas as gpd
import datetime

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

def dataNearTargetDate(stationID, targetDate):

    # stationID = nettlehamID
    # targetDate = dateOfInterest

    targetDate = datetime.datetime.strptime(targetDate, "%Y-%m-%d")

    startDate = targetDate - datetime.timedelta(days=5)
    startDate = datetime.datetime.strftime(startDate, "%Y-%m-%d")
    endDate = targetDate + datetime.timedelta(days=5)
    endDate = datetime.datetime.strftime(endDate, "%Y-%m-%d")

    readingURL = "/data/readings.json"
    readingParams = {"station": stationID, "observedProperty": "waterLevel",
        "mineq-date": startDate, "period": 900, "maxeq-date": endDate} 
    response = requests.get(baseURL+readingURL, params=readingParams)
    if response.status_code == 200:
        levelMeasures = pd.json_normalize(response.json()["items"])
    else:
        raise Exception("API error {0}".format(response.status_code))

    levelMeasures = levelMeasures.sort_values('dateTime')

    return levelMeasures

stationsURL = "/id/stations.json"
stationsParams = {"_limit": 10}

##response = requests.get(baseURL+stationsURL, params=stationsParams)
##if response.status_code == 200:
##    
##    stations = response.json()["items"]
##
##    allStationInfo = []
##
##    for station in stations:
##        
##        stationInfo = {
##            "name": station["label"],
##            "river": station["riverName"],
##            "ref": station["RLOIid"],
##            "types": [typeDat["@id"] for typeDat in station["type"]]
##            }
##        allStationInfo.append(stationInfo)
##
##    allStationData = (pd.DataFrame(allStationInfo)
##                          .explode("types"))
##
##    print(allStationData.groupby("types").size())
##    #print(json.dumps(station, indent=2))
##
##else:
##
##    raise Exception("API error {0}".format(response.status_code))

query1 = {"status.label":"Active", "observedProperty": "waterLevel", "_limit": 5000}

response = requests.get(baseURL+stationsURL, params=query1)
if response.status_code == 200:
    levelStations = getStationsInfo(response)
else:
    raise Exception("API error {0}".format(response.status_code))

query2 = {"status.label":"Active", "observedProperty": "waterFlow", "_limit": 5000}

response = requests.get(baseURL+stationsURL, params=query2)
if response.status_code == 200:
    flowStations = getStationsInfo(response)
else:
    raise Exception("API error {0}".format(response.status_code))

levelStations["ref"] = levelStations["ref"].astype(str)
flowStations["ref"] = flowStations["ref"].astype(str)
allStations = (pd.merge(levelStations.assign(waterLevel = True),
                        flowStations.assign(waterFlow = True),#[["ref","waterFlow"]],
                        how="outer", on="ref"))

nUniqueStations = len(allStations)
allStations = (allStations.convert_dtypes()
                          .fillna({'waterLevel':False,'waterFlow':False}))

# Count stations with only one of desired measures
nLevelOnly = len(allStations.query("waterLevel and not(waterFlow)"))
nFlowOnly = len(allStations.query("not(waterLevel) and waterFlow"))
print("{0} stations have no Flow measure, {1} stations have no Level measure".format(nLevelOnly, nFlowOnly))

# Check data aligns for stations with both measures
stationsWithBoth = (allStations.query("waterLevel and waterFlow")
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

# Tidy
allStations['name'] = np.where(allStations.waterLevel, allStations.name_x, allStations.name_y)
allStations['river'] = np.where(allStations.waterLevel, allStations.river_x, allStations.river_y)
allStations['lat'] = np.where(allStations.waterLevel, allStations.lat_x, allStations.lat_y)
allStations['long'] = np.where(allStations.waterLevel, allStations.long_x, allStations.long_y)
stationsTidy = allStations[["ref", "name", "river", "waterLevel", "waterFlow", "lat", "long"]]

# Split into 4 categories and plot
missalignedStations = anyMisaligned[["ref"]].assign(misaligned = True)
missalignedStations["ref"] = missalignedStations["ref"].astype(str)
stationsTidy["ref"] = stationsTidy["ref"].astype(str)
stationsTidy = (pd.merge(stationsTidy, missalignedStations, how="left", on="ref")
                    .convert_dtypes()
                    .fillna({"misaligned": False}))
stationsTidy["cat"] = np.where(stationsTidy.waterLevel, "Level only", "Flow only")
stationsTidy["cat"] = np.where(stationsTidy.apply(lambda df: df.waterLevel and df.waterFlow, axis=1), "Both", stationsTidy.cat)
stationsTidy["cat"] = np.where(stationsTidy.misaligned, "Both (non-matching)", stationsTidy.cat)

# Geostuff
stationsGeo = gpd.GeoDataFrame(
    stationsTidy,
    geometry = gpd.points_from_xy(stationsTidy.long, stationsTidy.lat),
    crs = "EPSG:4326"
)
stationsGeo.explore(column="cat", tooltip = "name", popup = True, tiles = "CartoDB positron")

# Explore measurement data
nettlehamID = "a941c6ca-6b2e-45b3-a515-198c39d4ceaa"
stationURL = "/id/stations/"+nettlehamID+".json"
stationURL = "/id/stations/"+nettlehamID+"/measures.json"
nettlehamParams = {"station": nettlehamID}
response = requests.get(baseURL+stationURL)#, params=nettlehamParams)
print(json.dumps(response.json(), indent=2))
# Readings
readingURL = "/data/readings.json"
readingParams = {"station": nettlehamID, "observedProperty": "waterLevel",
    "mineq-date": "2023-01-01", "period": 86400, "valueType": "max"}#"maxeq-date": "2025-09-01"} # 
response = requests.get(baseURL+readingURL, params=readingParams)
if response.status_code == 200:
    levelMeasures = pd.json_normalize(response.json()["items"])
else:
    raise Exception("API error {0}".format(response.status_code))
dateCounts = levelMeasures["date"].value_counts()
dupDates = dateCounts.index[dateCounts > 1]
dayUIDs = levelMeasures.groupby("date").idxmax()["value"]
dayUIDs = dayUIDs.dropna()#(pd.notnull(dayUIDs))
measuresUnique = levelMeasures.iloc[dayUIDs,:]
measuresUnique.plot(x="date", y="value")

# Zoom in  on peak
measuresUnique = measuresUnique.sort_values('date')
measuresUnique = measuresUnique.assign(
    lastValue = lambda df: df.value.shift(1),
    nextValue = lambda df: df.value.shift(-1)
).assign(
    localMax = lambda df: (df.value > df.lastValue) & (df.value > df.nextValue)
)
maximums = measuresUnique.query('localMax')
peaks = maximums.sort_values('value', ascending=False).head(5)
dataAroundPeaks = pd.DataFrame()
for i in range(5):
    peakLoc = peaks.date.iloc[i]
    dataAroundPeak = dataNearTargetDate(nettlehamID, peakLoc)
    dataAroundPeak = dataAroundPeak.assign(peakDate = peakLoc)
    dataAroundPeak = dataAroundPeak.reset_index()
    dataAroundPeaks = pd.concat([dataAroundPeaks, dataAroundPeak])
valuesAroundPeaks = dataAroundPeaks.pivot(columns = 'peakDate', values = 'value')
valuesAroundPeaks.plot()#x='date',y='value')
