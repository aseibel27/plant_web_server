const outputCount = 4;
const buttonsContainer = document.getElementById('buttonsContainer');

function createPlantElement(plantIndex) {
  const plantDiv = document.createElement('div');
  plantDiv.className = 'plant';

  // Label
  const label = document.createElement('label');
  label.textContent = `Plant ${plantIndex + 1}`;
  plantDiv.appendChild(label);

  // Button
  const btn = document.createElement('button');
  btn.className = 'button';
  btn.textContent = 'Water';
  btn.addEventListener('mousedown', () => togglePump(plantIndex, true));
  btn.addEventListener('mouseup', () => togglePump(plantIndex, false));
  plantDiv.appendChild(btn);

  // Moisture display
  const moistP = document.createElement('p');
  moistP.className = 'moisture';
  moistP.innerHTML = `Moisture: <span id="moist${plantIndex + 1}">--</span>%`;
  plantDiv.appendChild(moistP);

  return plantDiv;
}

function setupUI() {
  buttonsContainer.innerHTML = ''; // Clear any previous content
  for (let i = 0; i < outputCount; i++) {
    buttonsContainer.appendChild(createPlantElement(i));
  }
}

function togglePump(plant, state) {
  const action = state ? 'on' : 'off';
  fetch(`/${action}/${plant}`).catch(console.error);
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
  const timeString = now.toLocaleString(); // includes both date and time
  document.getElementById('clock').textContent = timeString;
}

// Initialize UI and start updates
setupUI();
setInterval(updateMoisture, 1000);
setInterval(updateClock, 1000);
