// === main.js ===
const outputCount = 4;
const buttonsContainer = document.getElementById('buttonsContainer');

function createPlantElement(plantIndex) {
  const plantDiv = document.createElement('div');
  plantDiv.className = 'plant';

  const label = document.createElement('label');
  label.textContent = `Plant ${plantIndex + 1}`;
  plantDiv.appendChild(label);

  const btn = document.createElement('button');
  btn.className = 'button';
  btn.textContent = 'Water';
  btn.addEventListener('mousedown', () => togglePump(plantIndex, true));
  btn.addEventListener('mouseup', () => togglePump(plantIndex, false));
  plantDiv.appendChild(btn);

  const moistP = document.createElement('p');
  moistP.className = 'moisture';
  moistP.innerHTML = `Moisture: <span id="moist${plantIndex + 1}">--</span>%`;
  plantDiv.appendChild(moistP);

  return plantDiv;
}

function setupUI() {
  buttonsContainer.innerHTML = '';
  for (let i = 0; i < outputCount; i++) {
    buttonsContainer.appendChild(createPlantElement(i));
  }
}

function togglePump(plant, state) {
  fetch('/set_pump', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ id: plant, on: state })
  }).catch(console.error);
}

async function updateMoisture() {
  try {
    const res = await fetch('/moisture');
    const data = await res.json();
    for (let i = 1; i <= outputCount; i++) {
      const el = document.getElementById(`moist${i}`);
      if (el) el.textContent = data[`moist${i}`];
    }
  } catch (e) {
    console.error('Failed to fetch moisture data:', e);
  }
}

function updateClock() {
  const now = new Date();
  const timeString = now.toLocaleString();
  document.getElementById('clock').textContent = timeString;
}

setupUI();
setInterval(updateMoisture, 1000);
setInterval(updateClock, 1000);