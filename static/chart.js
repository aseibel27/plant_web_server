const ctx = document.getElementById('moistureChart').getContext('2d');

let currentHistoryType = 'seconds'; // 'seconds' or 'minutes'
const labels = Array.from({ length: 60 }, (_, i) => `${59 - i}`);

const moistureChart = new Chart(ctx, {
  type: 'line',
  data: {
    labels,
    datasets: [
      { label: 'Plant 1', data: Array(60).fill(null), borderColor: 'red', fill: false },
      { label: 'Plant 2', data: Array(60).fill(null), borderColor: 'green', fill: false },
      { label: 'Plant 3', data: Array(60).fill(null), borderColor: 'blue', fill: false },
      { label: 'Plant 4', data: Array(60).fill(null), borderColor: 'orange', fill: false },
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
        title: { display: true, text: 'Moisture (%)' },
      },
      x: {
        title: { display: true, text: 'Time ago (s)' },
      },
    },
  },
});

async function updateGraph() {
  try {
    const res = await fetch('/history');
    const data = await res.json();

    if (currentHistoryType === 'hours') {
      // Use hourLabels as x-axis labels
      const now = new Date();
      const hourLabels = [];
      for (let i = 59; i >= 0; i--) {
        const pastHour = new Date(now.getTime() - i * 60 * 60 * 1000);
        const label = pastHour.getFullYear() + '-' +
              String(pastHour.getMonth() + 1).padStart(2, '0') + '-' +
              String(pastHour.getDate()).padStart(2, '0') + ' ' +
              String(pastHour.getHours()).padStart(2, '0') + ':00';
        hourLabels.push(label);
      }
      moistureChart.data.labels = hourLabels;

      for (let i = 0; i < 4; i++) {
        moistureChart.data.datasets[i].data = data[`hours${i + 1}`];
      }

      // Update X axis title
      moistureChart.options.scales.x.title.text = 'Time (hourly)';
    } else {
      // Use relative "time ago" labels
      moistureChart.data.labels = Array.from({ length: 60 }, (_, i) => `${59 - i}`);

      for (let i = 0; i < 4; i++) {
        const key = `${currentHistoryType}${i + 1}`;
        const historyData = data[key];
        moistureChart.data.datasets[i].data = historyData.concat(Array(60 - historyData.length).fill(null)).slice(-60);
      }

      // Update X axis title
      moistureChart.options.scales.x.title.text =
        currentHistoryType === 'seconds' ? 'Time ago (s)' : 'Time ago (min)';
    }

    moistureChart.update();
  } catch (e) {
    console.error('Failed to fetch history data:', e);
  }
}


document.getElementById('historySelect').addEventListener('change', (e) => {
  currentHistoryType = e.target.value;
  updateGraph(); // immediately refresh chart with new data type
});


updateGraph();
setInterval(updateGraph, 1000);
