const sessionId = Math.random().toString().substring(10);
const sse_url = "http://" + window.location.host + "/events/" + sessionId;
const send_url = "http://" + window.location.host + "/send/" + sessionId;
const upload_url = "http://" + window.location.host + "/upload/" + sessionId; // New upload URL
let eventSource = null;
let is_audio = false;

// Get DOM elements
const messageForm = document.getElementById("messageForm");
const messageInput = document.getElementById("message");
const messagesDiv = document.getElementById("messages");
const attachmentButton = document.getElementById("attachmentButton"); // New
const fileInput = document.getElementById("fileInput"); // New
let currentMessageId = null;

// SSE handlers
function connectSSE() {
  // Connect to SSE endpoint
  eventSource = new EventSource(sse_url + "?is_audio=" + is_audio);

  // Handle connection open
  eventSource.onopen = function () {
    console.log("SSE connection opened.");
    messagesDiv.innerHTML = "";
    document.getElementById("sendButton").disabled = false;
    addSubmitHandler();
  };

  // Handle incoming messages
  eventSource.onmessage = function (event) {
    const message_from_server = JSON.parse(event.data);
    console.log("[AGENT TO CLIENT] ", message_from_server);

    

    if (message_from_server.turn_complete && message_from_server.turn_complete == true) {
      currentMessageId = null;
      return;
    }

    if (message_from_server.interrupted && message_from_server.interrupted === true) {
      if (audioPlayerNode) {
        audioPlayerNode.port.postMessage({ command: "endOfAudio" });
      }
      return;
    }

    if (message_from_server.mime_type == "audio/pcm" && audioPlayerNode) {
      audioPlayerNode.port.postMessage(base64ToArray(message_from_server.data));
    }

    if (message_from_server.mime_type == "text/plain") {
      if (currentMessageId == null) {
        currentMessageId = Math.random().toString(36).substring(7);
        const message = document.createElement("p");
        message.id = currentMessageId;
        messagesDiv.appendChild(message);
      }
      const message = document.getElementById(currentMessageId);
      message.textContent += message_from_server.data;
      messagesDiv.scrollTop = messagesDiv.scrollHeight;
    }
  };

  // Handle connection close
  eventSource.onerror = function (event) {
    console.log("SSE connection error or closed.");
    document.getElementById("sendButton").disabled = true;
    const p = document.createElement("p");
    p.className = 'system-message';
    p.textContent = "Connection closed. Reconnecting...";
    messagesDiv.appendChild(p);
    eventSource.close();
    setTimeout(function () {
      console.log("Reconnecting...");
      connectSSE();
    }, 5000);
  };
}
connectSSE();

// Add submit handler to the form
function addSubmitHandler() {
  messageForm.onsubmit = function (e) {
    e.preventDefault();
    const message = messageInput.value;
    if (message) {
      const p = document.createElement("p");
      // Display user message with the new style
      p.className = "user-message";
      p.textContent = message;
      messagesDiv.appendChild(p);
      messagesDiv.scrollTop = messagesDiv.scrollHeight;
      messageInput.value = "";
      sendMessage({
        mime_type: "text/plain",
        data: message,
      });
      console.log("[CLIENT TO AGENT] " + message);
    }
    return false;
  };
}

// 1. FILE UPLOAD LOGIC
attachmentButton.addEventListener("click", () => {
  fileInput.click();
});

fileInput.addEventListener("change", (event) => {
  const file = event.target.files[0];
  if (file) {
    uploadFile(file);
  }
  // Reset file input to allow uploading the same file again
  fileInput.value = "";
});

async function uploadFile(file) {
  const formData = new FormData();
  formData.append("file", file);

  const p = document.createElement("p");
  p.className = "system-message";
  p.textContent = `Uploading ${file.name}...`;
  messagesDiv.appendChild(p);
  messagesDiv.scrollTop = messagesDiv.scrollHeight;

  try {
    const response = await fetch(upload_url, {
      method: "POST",
      body: formData,
    });
    const result = await response.json();
    if (!response.ok) {
      p.textContent = `Error uploading ${file.name}: ${result.detail || 'Server error'}`;
    } else {
      p.textContent = `Successfully uploaded and parsed ${file.name}.`;
      // The server will handle sending the parsed text into the conversation
    }
  } catch (error) {
    console.error("Error uploading file:", error);
    p.textContent = `Failed to upload ${file.name}.`;
  }
}

// (The rest of the file: sendMessage, base64ToArray, Audio handling, etc. remains the same)
// ... (keep the rest of your app.js code from the sendMessage function onwards) ...
async function sendMessage(message) {
  const isTextMessage = message.mime_type === "text/plain";
  const sendButton = document.getElementById("sendButton");

  if (isTextMessage) {
    sendButton.disabled = true;
  }

  try {
    const response = await fetch(send_url, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(message),
    });

    if (!response.ok) {
      console.error("Failed to send message:", response.statusText);
    }
  } catch (error) {
    console.error("Error sending message:", error);
  } finally {
    if (isTextMessage) {
      sendButton.disabled = false;
    }
  }
}

function base64ToArray(base64) {
  const binaryString = window.atob(base64);
  const len = binaryString.length;
  const bytes = new Uint8Array(len);
  for (let i = 0; i < len; i++) {
    bytes[i] = binaryString.charCodeAt(i);
  }
  return bytes.buffer;
}

let audioPlayerNode;
let audioPlayerContext;
let audioRecorderNode;
let audioRecorderContext;
let micStream;
let audioBuffer = [];
let bufferTimer = null;
import { startAudioPlayerWorklet } from "./audio-player.js";
import { startAudioRecorderWorklet } from "./audio-recorder.js";

function startAudio() {
  startAudioPlayerWorklet().then(([node, ctx]) => {
    audioPlayerNode = node;
    audioPlayerContext = ctx;
  });
  startAudioRecorderWorklet(audioRecorderHandler).then(
    ([node, ctx, stream]) => {
      audioRecorderNode = node;
      audioRecorderContext = ctx;
      micStream = stream;
    }
  );
}

const startAudioButton = document.getElementById("startAudioButton");
const stopAudioButton = document.getElementById("stopAudioButton");

startAudioButton.addEventListener("click", () => {
  startAudioButton.disabled = true;
  stopAudioButton.disabled = false;
  startAudio();
  is_audio = true;
  eventSource.close(); 
  connectSSE(); 
});

stopAudioButton.addEventListener("click", () => {
  startAudioButton.disabled = false;
  stopAudioButton.disabled = true;
  stopAudioRecording();
  micStream.getTracks().forEach(track => track.stop());
  is_audio = false;
  eventSource.close(); 
  connectSSE(); 
  const p = document.createElement("p");
  p.className = 'system-message'; // Use system message style
  p.textContent = "Transcribing final audio...";
  messagesDiv.appendChild(p);
});

function audioRecorderHandler(pcmData) {
  audioBuffer.push(new Uint8Array(pcmData));
  if (!bufferTimer) {
    bufferTimer = setInterval(sendBufferedAudio, 200);
  }
}

function sendBufferedAudio() {
  if (audioBuffer.length === 0) {
    return;
  }
  let totalLength = 0;
  for (const chunk of audioBuffer) {
    totalLength += chunk.length;
  }
  const combinedBuffer = new Uint8Array(totalLength);
  let offset = 0;
  for (const chunk of audioBuffer) {
    combinedBuffer.set(chunk, offset);
    offset += chunk.length;
  }
  sendMessage({
    mime_type: "audio/pcm",
    data: arrayBufferToBase64(combinedBuffer.buffer),
  });
  console.log("[CLIENT TO AGENT] sent %s bytes", combinedBuffer.byteLength);
  audioBuffer = [];
}

function stopAudioRecording() {
  if (bufferTimer) {
    clearInterval(bufferTimer);
    bufferTimer = null;
  }
  if (audioBuffer.length > 0) {
    sendBufferedAudio();
  }
}

function arrayBufferToBase64(buffer) {
  let binary = "";
  const bytes = new Uint8Array(buffer);
  const len = bytes.byteLength;
  for (let i = 0; i < len; i++) {
    binary += String.fromCharCode(bytes[i]);
  }
  return window.btoa(binary);
}