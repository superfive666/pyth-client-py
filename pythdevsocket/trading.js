// global information
let SYMBOL = undefined;

window.addEventListener("DOMContentLoaded", () => {
  const chart = LightweightCharts.createChart(
    document.getElementById("chart-container"),
    {
      width: 900,
      height: 600,
      crosshair: {
        mode: LightweightCharts.CrosshairMode.Normal,
      },
    }
  );

  const candleSeries = chart.addCandlestickSeries();
  candleSeries.setData([]);

  let currentTicks = 0;
  let currentTime = new Date().getTime();

  const currentBar = {
    open: null,
    high: null,
    low: null,
    close: null,
    time: currentTime,
  };

  const mergeTickToBar = (price) => {
    if (currentBar.open === null) {
      currentBar.open = price;
      currentBar.high = price;
      currentBar.low = price;
      currentBar.close = price;
    } else {
      currentBar.close = price;
      currentBar.high = Math.max(currentBar.high, price);
      currentBar.low = Math.min(currentBar.low, price);
    }
    currentBar.time = new Date().getTime();

    candleSeries.update(currentBar);

    if (++currentTicks === 30) {
      currentTime = new Date().getTime();

      currentBar.open = null;
      currentBar.high = null;
      currentBar.low = null;
      currentBar.close = null;
      currentBar.time = currentTime;

      currentTicks = 0;
    }
  }

  const websocket = new WebSocket("ws://localhost:6789/");

  websocket.onmessage = ({ data }) => {
    const event = JSON.parse(data);
    switch (event.type) {
      case "message":
        console.log("Connected with message from server:", event.content);
        break;
      case "price":
        console.log(event);
        // handle first time hearing the symbol
        if (!SYMBOL) {
          SYMBOL = event.symbol;
          const p = document.createElement("p");
          p.style.cssText = "color: white; ";
          p.innerHTML = "Trading Symbol: " + SYMBOL;
          const info = document.getElementById("symbol-info");
          info.append(p);
        }

        // handling pushing data to charts
        mergeTickToBar(event.price);
        break;
    }
  };
});
