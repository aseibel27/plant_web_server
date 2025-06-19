const ctx = document.getElementById("moistureChart").getContext("2d");

let currentHistoryType = "seconds";

// Precompute reversed labels once (59 on left, 0 on right)
const reversedLabels = Array.from({ length: 60 }, (_, i) => 59 - i);

const moistureChart = new Chart(ctx, {
  type: "line",
  data: {
    labels: reversedLabels,
    datasets: [
      {
        label: "Plant 1",
        data: Array(60).fill(null),
        borderColor: "red",
        fill: false,
      },
      {
        label: "Plant 2",
        data: Array(60).fill(null),
        borderColor: "green",
        fill: false,
      },
      {
        label: "Plant 3",
        data: Array(60).fill(null),
        borderColor: "blue",
        fill: false,
      },
      {
        label: "Plant 4",
        data: Array(60).fill(null),
        borderColor: "orange",
        fill: false,
      },
      {
        label: "Temperature (°F)",
        data: Array(60).fill(null),
        borderColor: "magenta",
        fill: false,
        yAxisID: "y2",
      },
      {
        label: "Humidity (%)",
        data: Array(60).fill(null),
        borderColor: "cyan",
        fill: false,
      },
    ],
  },
  options: {
    responsive: true,
    animation: false,
    maintainAspectRatio: false,
    scales: {
      y: {
        min: 0,
        max: 100,
        title: { display: true, text: "Moisture | Humidity (%)" },
      },
      y2: {
        min: 30,
        max: 120,
        position: "right",
        title: { display: true, text: "Temperature (°F)" },
        grid: { drawOnChartArea: false },
      },
      x: {
        type: "category",
        reverse: false,
        title: { display: true, text: "Time" },
        ticks: {
          maxRotation: 45,
          minRotation: 45,
          autoSkip: true,
          maxTicksLimit: 15,
          callback: function (value) {
            const label = this.getLabelForValue(value);
            if (!label) return label;

            if (
              currentHistoryType === "hours" ||
              currentHistoryType === "days"
            ) {
              const dateObj = new Date(label);
              if (!isNaN(dateObj)) {
                const options =
                  currentHistoryType === "hours"
                    ? {
                        month: "short",
                        day: "numeric",
                        year: "numeric",
                        hour: "numeric",
                      }
                    : { month: "short", day: "numeric", year: "numeric" };

                return dateObj.toLocaleDateString(undefined, options);
              }
            }
            return label;
          },
        },
      },
    },
  },
});

async function updateGraph() {
  try {
    const res = await fetch(`/history?type=${currentHistoryType}`);
    const data = await res.json();

    const time = data.time || Array(60).fill("");

    if (currentHistoryType === "seconds" || currentHistoryType === "minutes") {
      moistureChart.data.labels = reversedLabels;
    } else {
      moistureChart.data.labels = time;
    }

    const padLength =
      currentHistoryType === "seconds" || currentHistoryType === "minutes"
        ? reversedLabels.length
        : time.length;

    for (let i = 0; i < 6; i++) {
      const key = `sensor${i + 1}`;
      const values = Array.isArray(data[key]) ? data[key] : [];

      const padded = values
        .concat(Array(padLength - values.length).fill(null))
        .slice(0, padLength);

      const cleaned = padded.map((v) =>
        v === null || v === -1 || v === "-1" ? null : Number(v),
      );

      const finalData =
        currentHistoryType === "seconds" || currentHistoryType === "minutes"
          ? cleaned.slice().reverse()
          : cleaned;

      moistureChart.data.datasets[i].data = finalData;
    }

    const xLabel = {
      seconds: "Time ago (s)",
      minutes: "Time ago (min)",
      hours: "Time (hourly)",
      days: "Date",
    }[currentHistoryType];

    moistureChart.options.scales.x.title.text = xLabel;
    moistureChart.update();
  } catch (e) {
    console.error("Failed to fetch or render history data:", e);
  }
}

document.getElementById("historySelect").addEventListener("change", (e) => {
  currentHistoryType = e.target.value;
  updateGraph();
});

updateGraph();
setInterval(updateGraph, 1000);
