import requests
import json
#import numpy as np
import pandas as pd
import datetime

baseURL = "http://environment.data.gov.uk/hydrology"

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