import dash
import schedule
from scipy import signal
import plotly
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import pandas as pd
import numpy as np
import time

from dateutil import parser
import urllib.request, json 
import requests
from dash import Dash, dcc, html, Input, Output
import plotly
from dash.dependencies import Input, Output

import json
import datetime
import os


from datetime import date as date_func

def get_kline(startTime,endTime,limit,symbol,interval):
    
    if interval[-1] == 'm':
        endTime = int(startTime+(limit*int(interval[:-1])*60*1500))
        
    data = requests.get('https://fapi.binance.com/fapi/v1/klines', params={"symbol" : symbol,
                                                        "interval" : interval, 
                                                        "startTime" : startTime,
                                                        "endTime"   : endTime,
                                                        "limit": limit}).json()
    #data  = pd.DataFrame(data)
    data  = pd.DataFrame(data,columns = ['timestamp', 'open', 'high', 'low', 'close', 'volume', 'close_time', 'quote_vol', 'no_of_trades', 'tb_base_vol', 'tb_quote_vol', 'ignore' ])
    data.iloc[:,1:]=data.iloc[:,1:].astype(float)
    data['time'] = pd.to_datetime(data['timestamp'], unit='ms')
    return data



def get_kline_lookback(symbol,interval,start_date,end_date):
    start_date = datetime.datetime.strptime(start_date, "%d/%m/%Y")
    start_date = datetime.datetime.timestamp(start_date)
    #convert to nanoseconds
    start_date = int(start_date*1000)

    end_date = datetime.datetime.strptime(end_date, "%d/%m/%Y")
    end_date = datetime.datetime.timestamp(end_date)
    #convert to nanoseconds
    end_date = int(end_date*1000)

    time_del = end_date-start_date
    timestep = int(interval[:-1])*1e6
    limit = int(time_del/timestep)
    
    if interval[-1] == 'm':
        no_loop     = round(time_del/(timestep*60))+1 
        print('loops',no_loop)
        timestep_ms = timestep*timestep*60
    elif interval[-1] == 'h':
        no_loop  = round(time_del/(timestep*60*60))+1
        print('loops',no_loop)
        timestep_ms = timestep*timestep*60*60
    elif interval[-1] == 'd':
        no_loop  = round(time_del/(timestep*24*60*60))+1
        print('loops',no_loop)
        timestep_ms = timestep*timestep*24*60*60

    #download the historical price, you can change the candle resolution
    kline = get_kline(startTime=start_date,endTime=int(start_date+timestep_ms),limit=1000,symbol=symbol,interval=interval)
    
    for i in range(no_loop):
        kline_temp = get_kline(startTime=kline['timestamp'].values[-1],endTime=int(kline['timestamp'].values[-1].astype(float)+timestep_ms) ,limit=1000,symbol=symbol,interval=interval)
        kline=pd.concat([kline,kline_temp]).drop_duplicates().reset_index(drop=True)
        
    kline=pd.concat([kline,kline_temp]).drop_duplicates().reset_index(drop=True)
    kline = kline.groupby('timestamp').mean().reset_index() #getting rid of the repeated values
    kline['time'] = pd.to_datetime(kline['timestamp'], unit='ms')
    return kline



#get unique tickers 24hr Ticker Price Change Statistics from biannce api
#GET /fapi/v1/ticker/24hr 
def get_tickers():
    url = 'https://fapi.binance.com/fapi/v1/ticker/24hr'
    response = requests.get(url)
    data = response.json()
    #to pandas dataframe
    #df = pd.DataFrame(data)
    #rename columns
    #df.rename(columns={'symbol':'Ticker', 'priceChange':'Price Change', 'priceChangePercent':'Price Change Percent'}, inplace=True)
    df = pd.DataFrame(data)
    df['quoteVolume'] = df['quoteVolume'].astype(float)
    df =df.sort_values(['quoteVolume'], ascending=False)
    
    #drop columns
    return df['symbol'].values#['Ticker']

tickers = get_tickers()

app = Dash(__name__)
server = app.server

app.layout = html.Div([


   
    dcc.Dropdown(id='Ticker',
                options=tickers,
                multi=False,
                value=tickers,
                className='Ticker'),

    dcc.Dropdown(id='TimeFrame',
                options=['1m','3m','5m','15m','30m','1h','2h','4h','6h','12h','1d','3d'],
                multi=False,
                #value=timeframe,
                className='TimeFrame'),

    dcc.Input(id="start_date", type="text", placeholder="Start Date (DD//MM/YYYY)"  , style={'marginRight':'25px'}),
    dcc.Input(id="end_date"  , type="text", placeholder="End Date   (DD//MM/YYYY)"  , style={'marginRight':'25px'}),
    dcc.Input(id="Regression Window", 
              type='number', min=1, max=None, step=1,
              placeholder="Regression Smoothing",
              className='regression_window' , style={'marginRight':'25px'}),

    dcc.Input(id="Volatility Window", 
              type='number', min=1, max=None, step=1,
              placeholder="Volatility Smoothing",
              className='volatility_window' , style={'marginRight':'25px'}),
    

                
    dcc.Interval(
            id='refresh',
            interval=10000, 
            n_intervals=0
        ), 

    dcc.Graph(id='live-update-graph')
    ]) 

@app.callback(
    Output(component_id='live-update-graph', component_property='figure'),
    [ 
     Input('start_date', 'value'),
     Input('end_date', 'value'),
     Input("Ticker", "value"),
     Input("TimeFrame", "value"),
     Input("Regression Window", "value"),
     Input("Volatility Window", "value")
    ])


def update_graph(start_date,end_date,Ticker,TimeFrame,regression_window,volatility_window):   
    
    if start_date == None:
        start_date =(datetime.datetime.today()-datetime.timedelta(days=30)).strftime('%d/%m/%Y')

    if end_date == None:
        end_date = datetime.datetime.today().strftime('%d/%m/%Y')

    if regression_window == None:
        regression_window = 30
    if volatility_window == None:
        volatility_window = 30

   
    kline = get_kline_lookback(symbol=Ticker,interval=TimeFrame,start_date=start_date,end_date=end_date)

    #calculate the rolling mean and standard deviation of percentage change in close price
    percentage_change = kline['close'].pct_change()
    percentage_change_std = percentage_change.rolling(window=volatility_window).std()

    #calculae the regression line of close price 
    close_price_regression = pd.DataFrame(columns=['time', 'close'])
    close_price_regression['time'] = kline['time']
    close_price_regression['close'] = kline['close'].ewm(span=2).mean()
    close_price_regression['close_regression'] = close_price_regression['close'].rolling(window=regression_window).apply(lambda x: np.polyfit(x.index, x, 1)[0])

        
        
    layout = dict(
        #height = 600,
        mapbox = dict(
            uirevision='no reset of zoom',
            style = 'light'
        ),
    )

    #plot the regression line the below subplot
    #subplot with 2 rows and 1 column using plotly
    fig = make_subplots(rows=3, cols=1, row_heights=[0.5, 0.15,0.15], vertical_spacing=0.02,shared_xaxes=True)
    
    #add title of the plot
    fig.update_layout(title_text=f'{Ticker} Risk Analysis')
    fig.add_trace(go.Scatter(x=kline['time'], y=kline['close'],name=' Close Price'), row=1, col=1)
    fig.add_trace(go.Scatter(x=kline['time'], y=close_price_regression['close_regression'], name='Regression Gradient'), row=2, col=1)

    #fig.add_trace(go.Scatter(x=kline['time'], y=percentage_change_std, name='mean'), row=3, col=1)
    #add EMA of percentage change std
    fig.add_trace(go.Scatter(x=kline['time'], y=percentage_change_std.ewm(span=50).mean(), name='Volatility'), row=3, col=1)

    #custom plot width and height
 
    #share x-axis







    fig.update_layout(showlegend=True)
    fig.update_layout(height=800,margin=dict( b=30)) 
    fig.update_layout(
    autosize=True,
    #scaleratio=1
    #width=1200,
    #height=800,
    yaxis=dict(
        title_text="Price / USDT",
        #titlefont=dict(size=30),
    )



)
    fig.update_layout(xaxis_rangeslider_visible=False)
    fig.update_layout(uirevision=True) 
    #fig.update_layout(title={
    #    'text': f'BTC-ALT correlations 1m Timeframe',
    #    #'y':0.9,
    #    #'x':0.5,
    #    'xanchor': 'left',
    #    'yanchor': 'top'})
    return fig
    
    return  #price_plot(altcoin=Ticker)

if __name__ == '__main__':
    app.run_server(debug=False)

    

