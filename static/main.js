const outputCount = 4;
const buttonsContainer = document.getElementById("buttonsContainer");

// === Create a plant element (pump + moisture display) ===
function createPlantElement(plantIndex) {
  const plantDiv = document.createElement("div");
  plantDiv.className = "plant";

  const label = document.createElement("label");
  label.textContent = `Plant ${plantIndex + 1}`;
  plantDiv.appendChild(label);

  const btn = document.createElement("button");
  btn.className = "button";
  btn.textContent = "Water";
  btn.addEventListener("mousedown", () => togglePump(plantIndex, true));
  btn.addEventListener("mouseup", () => togglePump(plantIndex, false));
  btn.addEventListener("touchstart", () => togglePump(plantIndex, true));
  btn.addEventListener("touchend", () => togglePump(plantIndex, false));
  plantDiv.appendChild(btn);

  const moistP = document.createElement("p");
  moistP.className = "moisture";
  moistP.innerHTML = `Moisture: <span id="moist${plantIndex + 1}">--</span>%`;
  plantDiv.appendChild(moistP);

  return plantDiv;
}

// === Add extra readout for temp & humidity ===
function createEnvReadout() {
  const envDiv = document.createElement("div");
  envDiv.className = "env";

  const temp = document.createElement("p");
  temp.innerHTML = `Temp: <span id="temp">--</span>°F`;
  envDiv.appendChild(temp);

  const hum = document.createElement("p");
  hum.innerHTML = `Humidity: <span id="hum">--</span>%`;
  envDiv.appendChild(hum);

  return envDiv;
}

function setupUI() {
  buttonsContainer.innerHTML = "";
  for (let i = 0; i < outputCount; i++) {
    buttonsContainer.appendChild(createPlantElement(i));
  }

  buttonsContainer.appendChild(createEnvReadout());
}

// === Send pump control command ===
function togglePump(plant, state) {
  fetch("/set_pump", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ id: plant, on: state }),
  }).catch(console.error);
}

// === Update moisture and environment readings ===
async function updateMoisture() {
  try {
    const res = await fetch("/moisture");
    const data = await res.json();

    for (let i = 1; i <= outputCount; i++) {
      const el = document.getElementById(`moist${i}`);
      const val = data[`moist${i}`];
      if (el) el.textContent = val === -1 ? "--" : val;
    }

    if ("temp" in data) {
      const tempEl = document.getElementById("temp");
      if (tempEl) tempEl.textContent = data.temp === -1 ? "--" : data.temp;
    }

    if ("hum" in data) {
      const humEl = document.getElementById("hum");
      if (humEl) humEl.textContent = data.hum === -1 ? "--" : data.hum;
    }
  } catch (e) {
    console.error("Failed to fetch sensor data:", e);
  }
}

// === Update online/offline status ===
async function updateStatus() {
  try {
    const res = await fetch("/status");
    const { status } = await res.json();

    const light = document.getElementById("statusLight");
    const text = document.getElementById("statusText");

    if (status === "online") {
      light.style.backgroundColor = "limegreen";
      text.textContent = "Online";
    } else {
      light.style.backgroundColor = "red";
      text.textContent = "Offline";
    }
  } catch (e) {
    console.error("Failed to fetch status:", e);
  }
}

// === Clock update ===
function updateClock() {
  const now = new Date();
  const timeString = now.toLocaleString();
  document.getElementById("clock").textContent = timeString;
}

setupUI();
setInterval(updateMoisture, 1000);
setInterval(updateStatus, 1000);
setInterval(updateClock, 1000);
