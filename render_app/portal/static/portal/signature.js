(() => {
  const canvas = document.getElementById("signature-pad");
  const form = document.getElementById("signature-form");
  const hidden = document.getElementById("id_signature_data");
  const clear = document.getElementById("clear-signature");
  if (!canvas || !form || !hidden || !clear) return;

  const ctx = canvas.getContext("2d", { alpha: true });
  ctx.lineCap = "round";
  ctx.lineJoin = "round";
  ctx.strokeStyle = "#10243d";
  ctx.lineWidth = 4;
  let drawing = false;
  let hasInk = false;

  function point(event) {
    const rect = canvas.getBoundingClientRect();
    const x = (event.clientX - rect.left) * (canvas.width / rect.width);
    const y = (event.clientY - rect.top) * (canvas.height / rect.height);
    return { x, y };
  }

  canvas.addEventListener("pointerdown", (event) => {
    drawing = true;
    hasInk = true;
    canvas.setPointerCapture(event.pointerId);
    const p = point(event);
    ctx.beginPath();
    ctx.moveTo(p.x, p.y);
  });
  canvas.addEventListener("pointermove", (event) => {
    if (!drawing) return;
    const p = point(event);
    ctx.lineTo(p.x, p.y);
    ctx.stroke();
  });
  function stop(event) {
    drawing = false;
    if (event.pointerId !== undefined && canvas.hasPointerCapture(event.pointerId)) canvas.releasePointerCapture(event.pointerId);
  }
  canvas.addEventListener("pointerup", stop);
  canvas.addEventListener("pointercancel", stop);
  clear.addEventListener("click", () => {
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    hidden.value = "";
    hasInk = false;
  });
  form.addEventListener("submit", (event) => {
    if (!hasInk) {
      event.preventDefault();
      canvas.focus();
      alert("Draw your signature before continuing.");
      return;
    }
    hidden.value = canvas.toDataURL("image/png");
  });
})();
