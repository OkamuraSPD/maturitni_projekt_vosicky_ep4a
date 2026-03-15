let currentChart = null;
let currentTarget = { device_id: null, pin: null, horizon: "10m" };

async function fetchMonitor() {
  const root = document.getElementById("monitorRoot");
  if (!root) {
    return;
  }

  const room = (document.getElementById("filterRoom")?.value || "").trim().toLowerCase();
  const deviceFilter = (document.getElementById("filterDevice")?.value || "").trim().toLowerCase();
  const signal = (document.getElementById("filterSignal")?.value || "").trim().toLowerCase();

  const response = await fetch("/api/monitor_data");
  const data = await response.json();

  if (!data.ok) {
    root.innerHTML = "<p class='alert'>Chyba při načítání monitoru.</p>";
    return;
  }

  let html = "";

  for (const device of data.devices || []) {
    if (room && (device.room || "").toLowerCase().indexOf(room) === -1) {
      continue;
    }

    if (deviceFilter && (device.id || "").toLowerCase().indexOf(deviceFilter) === -1) {
      continue;
    }

    const pins = (device.pins || []).filter(pin => {
      if (!signal) {
        return true;
      }
      return (pin.signal || "").toLowerCase() === signal;
    });

    html += `<div class="card">
      <h3>${device.id} <small>(${device.room || ""})</small> — <span class="${device.online ? "ok" : "bad"}">${device.online ? "ONLINE" : "OFFLINE"}</span></h3>
      <div class="muted">IP: ${device.ip || ""} | Board: ${device.board || ""}</div>
      <table>
        <tr><th>Pin</th><th>Signal</th><th>Peripheral</th><th>Raw</th><th>Display</th><th>Graf</th></tr>
        ${pins.map(pin => {
          const isAnalog = (pin.signal || "").toLowerCase() === "analog";
          const openBtn = isAnalog ? `<button class="openChartBtn" data-dev="${device.id}" data-pin="${pin.pin}">Open</button>` : "—";
          const displayValue = pin.unit ? `${pin.display_value} ${pin.unit}` : `${pin.display_value}`;
          return `<tr>
            <td>${pin.pin}</td>
            <td>${pin.signal}</td>
            <td><span class="sensor-pill">${pin.icon || ""} ${pin.peripheral_id || "-"}</span></td>
            <td>${pin.raw_value}</td>
            <td>${displayValue}</td>
            <td>${openBtn}</td>
          </tr>`;
        }).join("")}
      </table>
    </div>`;
  }

  root.innerHTML = html || "<div class='card'><p class='muted'>Nic neodpovídá filtru nebo nejsou data.</p></div>";

  document.querySelectorAll(".openChartBtn").forEach(btn => {
    btn.addEventListener("click", () => {
      openModal(btn.dataset.dev, btn.dataset.pin);
    });
  });
}

function openModal(deviceId, pin) {
  currentTarget.device_id = deviceId;
  currentTarget.pin = pin;
  currentTarget.horizon = "10m";
  document.getElementById("modalTitle").textContent = `Graf: ${deviceId} pin ${pin}`;
  document.getElementById("modal").classList.remove("hidden");
  loadChart();
}

function closeModal() {
  document.getElementById("modal").classList.add("hidden");
  if (currentChart) {
    currentChart.destroy();
    currentChart = null;
  }
}

async function loadChart() {
  const { device_id, pin, horizon } = currentTarget;
  if (!device_id || !pin) {
    return;
  }

  const response = await fetch(`/api/measurements?device_id=${encodeURIComponent(device_id)}&pin=${encodeURIComponent(pin)}&horizon=${encodeURIComponent(horizon)}`);
  const data = await response.json();
  if (!data.ok) {
    return;
  }

  const labels = (data.series || []).map(item => new Date(item.ts * 1000).toLocaleTimeString());
  const values = (data.series || []).map(item => item.value);
  const canvas = document.getElementById("chartCanvas");

  if (currentChart) {
    currentChart.destroy();
  }

  currentChart = new Chart(canvas, {
    type: "line",
    data: {
      labels: labels,
      datasets: [{ label: "value", data: values }]
    }
  });
}

function setupMonitor() {
  const root = document.getElementById("monitorRoot");
  if (!root) {
    return;
  }

  document.getElementById("refreshBtn")?.addEventListener("click", fetchMonitor);
  document.getElementById("filterRoom")?.addEventListener("input", fetchMonitor);
  document.getElementById("filterDevice")?.addEventListener("input", fetchMonitor);
  document.getElementById("filterSignal")?.addEventListener("change", fetchMonitor);
  document.getElementById("closeModalBtn")?.addEventListener("click", closeModal);

  document.querySelectorAll(".hbtn").forEach(btn => {
    btn.addEventListener("click", () => {
      currentTarget.horizon = btn.dataset.h;
      loadChart();
    });
  });

  fetchMonitor();
  setInterval(fetchMonitor, 2000);
}

document.addEventListener("DOMContentLoaded", setupMonitor);
