import logging
from flask import Flask, render_template_string, request
from flask_socketio import SocketIO, emit, join_room, leave_room
import uuid

# --- CONFIGURATION ---
# Configure logging for production-grade output
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.config['SECRET_KEY'] = 'secret!'
# cors_allowed_origins="*" is used for development convenience
socketio = SocketIO(app, cors_allowed_origins="*")

# --- GLOBAL STATE ---
# In a production app, use Redis or a database.
waiting_users = []  # List of socket_ids waiting for a partner
active_pairs = {}   # Map socket_id -> partner_socket_id
users = {}          # Map socket_id -> {'name': str, 'gender': str, 'interest': str}
connected_users_count = 0 

# --- FRONTEND TEMPLATE (HTML/CSS/JS) ---
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Connect | Professional Video Chat</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/socket.io/4.0.1/socket.io.js"></script>
    <!-- Fonts & Icons -->
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap" rel="stylesheet">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    <script>
        tailwind.config = {
            theme: {
                extend: {
                    fontFamily: {
                        sans: ['Inter', 'sans-serif'],
                    },
                    colors: {
                        slate: {
                            850: '#1e293b', // Custom dark
                            900: '#0f172a',
                            950: '#020617',
                        }
                    }
                }
            }
        }
    </script>
    <style>
        body { font-family: 'Inter', sans-serif; }
        /* Only mirror local video, NOT remote video */
        video.mirrored { transform: scaleX(-1); }
        video { background-color: #0f172a; }
        
        .scrollbar-hide::-webkit-scrollbar { display: none; }
        .scrollbar-hide { -ms-overflow-style: none; scrollbar-width: none; }
        
        /* Glassmorphism utilities */
        .glass {
            background: rgba(30, 41, 59, 0.7);
            backdrop-filter: blur(10px);
            -webkit-backdrop-filter: blur(10px);
            border: 1px solid rgba(255, 255, 255, 0.05);
        }
        .glass-heavy {
            background: rgba(15, 23, 42, 0.9);
            backdrop-filter: blur(16px);
            border: 1px solid rgba(255, 255, 255, 0.1);
        }
    </style>
</head>
<body class="bg-slate-950 text-slate-200 h-screen flex flex-col overflow-hidden selection:bg-indigo-500 selection:text-white">

    <!-- Login/Signup Modal -->
    <div id="loginModal" class="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm transition-opacity duration-300">
        <div class="relative glass-heavy p-8 rounded-2xl shadow-2xl max-w-md w-full mx-4 transform transition-all scale-100">
            <!-- Close Button -->
            <button id="closeModalBtn" class="absolute top-4 right-4 text-slate-400 hover:text-white transition-colors hidden p-2 rounded-full hover:bg-slate-800">
                <i class="fas fa-times text-lg"></i>
            </button>

            <div class="text-center mb-8">
                <div class="inline-flex items-center justify-center w-16 h-16 rounded-full bg-indigo-500/10 text-indigo-400 mb-4">
                    <i class="fas fa-video text-3xl"></i>
                </div>
                <h2 class="text-3xl font-bold text-white tracking-tight">Welcome</h2>
                <p class="text-slate-400 mt-2">Connect randomly, chat privately.</p>
            </div>

            <form id="loginForm" class="space-y-5">
                <div class="space-y-2">
                    <label class="block text-xs font-semibold uppercase tracking-wider text-slate-500" for="username">Display Name</label>
                    <div class="relative">
                        <span class="absolute left-4 top-3.5 text-slate-500"><i class="fas fa-user"></i></span>
                        <input class="w-full bg-slate-900/50 text-white border border-slate-700 rounded-xl py-3 pl-10 pr-4 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent transition-all placeholder-slate-600" 
                            id="usernameInput" type="text" placeholder="How should we call you?" required autocomplete="off">
                    </div>
                </div>
                
                <div class="grid grid-cols-2 gap-4">
                    <div class="space-y-2">
                        <label class="block text-xs font-semibold uppercase tracking-wider text-slate-500">I am</label>
                        <div class="relative">
                            <select id="genderInput" class="w-full bg-slate-900/50 text-white border border-slate-700 rounded-xl py-3 px-4 appearance-none focus:outline-none focus:ring-2 focus:ring-indigo-500 transition-all cursor-pointer">
                                <option value="male">Male</option>
                                <option value="female">Female</option>
                            </select>
                            <span class="absolute right-4 top-3.5 text-slate-500 pointer-events-none"><i class="fas fa-chevron-down text-xs"></i></span>
                        </div>
                    </div>
                    <div class="space-y-2">
                        <label class="block text-xs font-semibold uppercase tracking-wider text-slate-500">Interested In</label>
                        <div class="relative">
                            <select id="interestInput" class="w-full bg-slate-900/50 text-white border border-slate-700 rounded-xl py-3 px-4 appearance-none focus:outline-none focus:ring-2 focus:ring-indigo-500 transition-all cursor-pointer">
                                <option value="any">Everyone</option>
                                <option value="male">Male</option>
                                <option value="female">Female</option>
                                <option value="both">Both</option>
                            </select>
                            <span class="absolute right-4 top-3.5 text-slate-500 pointer-events-none"><i class="fas fa-chevron-down text-xs"></i></span>
                        </div>
                    </div>
                </div>

                <button type="submit" 
                    class="w-full bg-gradient-to-r from-indigo-600 to-violet-600 hover:from-indigo-500 hover:to-violet-500 text-white font-semibold py-3.5 px-4 rounded-xl shadow-lg shadow-indigo-500/25 transition-all transform active:scale-[0.98] mt-2">
                    Start Matching
                </button>
            </form>
        </div>
    </div>

    <!-- Header -->
    <header class="h-16 glass z-40 flex items-center justify-between px-6 sticky top-0">
        <div class="flex items-center gap-3">
            <div class="relative flex h-3 w-3">
              <span class="animate-ping absolute inline-flex h-full w-full rounded-full bg-red-400 opacity-75"></span>
              <span class="relative inline-flex rounded-full h-3 w-3 bg-red-500"></span>
            </div>
            <h1 class="text-lg font-bold bg-clip-text text-transparent bg-gradient-to-r from-white to-slate-400">
                Connect<span class="text-indigo-500">.py</span>
            </h1>
        </div>

        <div class="flex items-center gap-3 md:gap-6">
             <div class="hidden md:flex items-center gap-2 px-3 py-1.5 rounded-full bg-slate-800/50 border border-slate-700/50 text-xs font-medium text-slate-300">
                <span class="w-2 h-2 bg-emerald-500 rounded-full shadow-[0_0_8px_rgba(16,185,129,0.5)]"></span>
                <span id="userCount">0 online</span>
            </div>
            
            <div id="status" class="text-xs font-mono text-slate-500 uppercase tracking-widest">Disconnected</div>

            <button id="editProfileBtn" class="hidden flex items-center justify-center w-8 h-8 rounded-full bg-slate-800 hover:bg-slate-700 border border-slate-700 text-slate-300 transition-all" title="Edit Profile">
                <i class="fas fa-user-gear"></i>
            </button>
        </div>
    </header>

    <!-- Main Content -->
    <main class="flex-1 flex flex-col md:flex-row overflow-hidden relative">
        
        <!-- Video Area -->
        <div class="flex-1 relative bg-black/40 flex flex-col justify-center items-center p-4 gap-4">
            
            <!-- Main Stage (Remote) -->
            <div class="relative w-full h-full max-h-[80vh] flex justify-center items-center overflow-hidden rounded-2xl bg-slate-900 shadow-2xl border border-slate-800">
                <!-- IMPORTANT: Removed 'mirrored' class from remote video so faces are not flipped -->
                <video id="remoteVideo" autoplay playsinline class="w-full h-full object-contain"></video>
                
                <!-- Empty State -->
                <div id="remotePlaceholder" class="absolute inset-0 flex flex-col items-center justify-center text-slate-500">
                    <div class="w-32 h-32 rounded-full bg-slate-800/50 flex items-center justify-center mb-6 border border-slate-700/50">
                        <i class="fas fa-video-slash text-5xl opacity-50"></i>
                    </div>
                    <h3 class="text-2xl font-semibold text-slate-300 mb-2">Ready to connect?</h3>
                    <p class="text-slate-500">Click "Next Stranger" to find a partner.</p>
                </div>

                <!-- Searching Overlay -->
                <div id="overlay" class="absolute inset-0 bg-slate-950/80 z-10 flex flex-col items-center justify-center hidden backdrop-blur-sm">
                    <div class="relative w-16 h-16 mb-4">
                        <div class="absolute inset-0 border-4 border-slate-700 rounded-full"></div>
                        <div class="absolute inset-0 border-4 border-indigo-500 rounded-full border-t-transparent animate-spin"></div>
                    </div>
                    <p class="text-white text-lg font-medium tracking-wide">Searching...</p>
                    <p class="text-slate-400 text-sm mt-1">Finding the best match for you</p>
                </div>
                
                <!-- Greeting Overlay (Hidden by default) -->
                <div id="greetingOverlay" class="absolute inset-0 z-30 flex flex-col items-center justify-center pointer-events-none hidden transition-all duration-700 ease-out opacity-0 translate-y-4">
                    <div class="glass-heavy px-8 py-6 rounded-3xl shadow-2xl text-center border border-indigo-500/30 ring-1 ring-white/10 transform transition-transform duration-500">
                        <div class="text-5xl mb-4 animate-bounce">👋</div>
                        <h3 class="text-2xl font-bold text-white mb-1">It's a Match!</h3>
                        <p class="text-slate-300">You are connected with <span id="greetingName" class="text-indigo-400 font-bold">Stranger</span>.</p>
                    </div>
                </div>

                <!-- Partner Info Overlay (Top Left) -->
                <div id="partnerInfoTag" class="absolute top-4 left-4 glass px-4 py-2 rounded-lg hidden flex items-center gap-2">
                    <div class="w-2 h-2 bg-red-500 rounded-full animate-pulse"></div>
                    <span id="partnerNameDisplay" class="font-medium text-sm">Stranger</span>
                </div>
            </div>

            <!-- Self View (Picture-in-Picture style) -->
            <div class="absolute bottom-6 right-6 w-32 md:w-56 aspect-video bg-slate-800 rounded-xl overflow-hidden border-2 border-slate-700/50 shadow-2xl z-20 group transition-transform hover:scale-105">
                <!-- Local video IS mirrored so it acts like a mirror -->
                <video id="localVideo" autoplay playsinline muted class="w-full h-full object-cover mirrored"></video>
                
                <!-- Media Controls (Hover) -->
                <div class="absolute inset-0 bg-black/40 flex items-center justify-center gap-3 opacity-0 group-hover:opacity-100 transition-opacity duration-200 backdrop-blur-[2px]">
                    <button id="toggleMicBtn" class="w-8 h-8 rounded-full bg-slate-200/20 hover:bg-white/90 hover:text-slate-900 text-white backdrop-blur-md flex items-center justify-center transition-all" title="Toggle Mic">
                        <i class="fas fa-microphone"></i>
                    </button>
                    <button id="toggleCamBtn" class="w-8 h-8 rounded-full bg-slate-200/20 hover:bg-white/90 hover:text-slate-900 text-white backdrop-blur-md flex items-center justify-center transition-all" title="Toggle Cam">
                        <i class="fas fa-video"></i>
                    </button>
                    <button id="shareScreenBtn" class="w-8 h-8 rounded-full bg-indigo-500/20 hover:bg-indigo-500 text-white backdrop-blur-md flex items-center justify-center transition-all" title="Share Screen">
                        <i class="fas fa-desktop"></i>
                    </button>
                </div>
            </div>
        </div>

        <!-- Chat Sidebar -->
        <div class="w-full md:w-[400px] bg-slate-900 border-l border-slate-800 flex flex-col h-[40vh] md:h-full z-30 shadow-2xl">
            
            <!-- Chat Log -->
            <div id="chatLog" class="flex-1 overflow-y-auto p-4 space-y-4">
                <div class="flex flex-col items-center justify-center h-full text-slate-500 space-y-2 opacity-50">
                    <i class="far fa-comments text-4xl mb-2"></i>
                    <p class="text-sm">Chat messages will appear here</p>
                </div>
            </div>

            <!-- Typing Indicator -->
            <div id="typingIndicator" class="h-6 px-6 text-xs text-indigo-400 font-medium italic hidden flex items-center gap-2">
                <div class="flex gap-1">
                    <span class="w-1 h-1 bg-indigo-400 rounded-full animate-bounce"></span>
                    <span class="w-1 h-1 bg-indigo-400 rounded-full animate-bounce delay-75"></span>
                    <span class="w-1 h-1 bg-indigo-400 rounded-full animate-bounce delay-150"></span>
                </div>
                <span id="typingName">Stranger</span> is typing...
            </div>

            <!-- Controls & Input Wrapper -->
            <div class="bg-slate-850 p-4 border-t border-slate-800 space-y-4">
                
                <!-- Main Action Buttons -->
                <div class="flex gap-3">
                    <button id="nextBtn" class="flex-1 group bg-slate-100 hover:bg-white text-slate-900 font-bold py-3 px-4 rounded-xl transition-all shadow-md active:scale-95 flex items-center justify-center gap-2">
                        <span>Next Stranger</span>
                        <i class="fas fa-arrow-right group-hover:translate-x-1 transition-transform"></i>
                    </button>
                    <button id="stopBtn" class="bg-slate-800 hover:bg-rose-500/10 hover:text-rose-500 hover:border-rose-500/50 border border-slate-700 text-slate-300 font-bold py-3 px-4 rounded-xl transition-all active:scale-95">
                        <i class="fas fa-stop"></i>
                    </button>
                </div>

                <!-- Chat Input -->
                <form id="chatForm" class="relative">
                    <input type="text" id="msgInput" placeholder="Type a message..." disabled
                        class="w-full bg-slate-900 text-white rounded-xl py-3.5 pl-4 pr-12 border border-slate-700 focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 focus:outline-none transition-all disabled:opacity-50 disabled:cursor-not-allowed placeholder-slate-500">
                    <button type="submit" id="sendBtn" disabled
                        class="absolute right-2 top-2 p-1.5 bg-indigo-600 hover:bg-indigo-500 text-white rounded-lg disabled:opacity-0 disabled:scale-75 transition-all shadow-lg">
                        <i class="fas fa-paper-plane text-xs"></i>
                    </button>
                </form>
                <div class="text-center text-[10px] text-slate-600">
                    Press <span class="font-mono bg-slate-800 px-1 rounded text-slate-400">ESC</span> to skip
                </div>
            </div>
        </div>
    </main>

    <script>
        const socket = io();
        const STORAGE_KEY = 'chat_user_profile_v2';

        // DOM Elements
        const localVideo = document.getElementById('localVideo');
        const remoteVideo = document.getElementById('remoteVideo');
        const nextBtn = document.getElementById('nextBtn');
        const stopBtn = document.getElementById('stopBtn');
        const chatForm = document.getElementById('chatForm');
        const msgInput = document.getElementById('msgInput');
        const chatLog = document.getElementById('chatLog');
        const statusEl = document.getElementById('status');
        const overlay = document.getElementById('overlay');
        const remotePlaceholder = document.getElementById('remotePlaceholder');
        const userCountEl = document.getElementById('userCount');
        const typingIndicator = document.getElementById('typingIndicator');
        const typingNameEl = document.getElementById('typingName');
        const toggleMicBtn = document.getElementById('toggleMicBtn');
        const toggleCamBtn = document.getElementById('toggleCamBtn');
        const shareScreenBtn = document.getElementById('shareScreenBtn');
        const partnerInfoTag = document.getElementById('partnerInfoTag');
        const partnerNameDisplay = document.getElementById('partnerNameDisplay');
        const greetingOverlay = document.getElementById('greetingOverlay');
        const greetingName = document.getElementById('greetingName');
        
        // Login & Profile Elements
        const loginModal = document.getElementById('loginModal');
        const loginForm = document.getElementById('loginForm');
        const usernameInput = document.getElementById('usernameInput');
        const genderInput = document.getElementById('genderInput');
        const interestInput = document.getElementById('interestInput');
        const editProfileBtn = document.getElementById('editProfileBtn');
        const closeModalBtn = document.getElementById('closeModalBtn');

        // Audio Context for Notifications (No external files needed)
        const audioCtx = new (window.AudioContext || window.webkitAudioContext)();

        function playNotification(type) {
            if (audioCtx.state === 'suspended') audioCtx.resume();
            
            const oscillator = audioCtx.createOscillator();
            const gainNode = audioCtx.createGain();
            
            oscillator.connect(gainNode);
            gainNode.connect(audioCtx.destination);
            
            const now = audioCtx.currentTime;

            if (type === 'match') {
                // Happy chime (Major Third)
                oscillator.type = 'sine';
                oscillator.frequency.setValueAtTime(523.25, now); // C5
                oscillator.frequency.linearRampToValueAtTime(659.25, now + 0.1); // E5
                
                gainNode.gain.setValueAtTime(0.1, now);
                gainNode.gain.exponentialRampToValueAtTime(0.01, now + 0.6);
                
                oscillator.start(now);
                oscillator.stop(now + 0.6);
            } else if (type === 'message') {
                // Soft pop
                oscillator.type = 'triangle';
                oscillator.frequency.setValueAtTime(800, now);
                
                gainNode.gain.setValueAtTime(0.05, now);
                gainNode.gain.exponentialRampToValueAtTime(0.01, now + 0.1);
                
                oscillator.start(now);
                oscillator.stop(now + 0.1);
            }
        }

        // WebRTC Config
        const peerConnectionConfig = {
            'iceServers': [
                {'urls': 'stun:stun.l.google.com:19302'},
                {'urls': 'stun:stun1.l.google.com:19302'}
            ]
        };

        let localStream;
        let screenStream; // Track the screen stream
        let peerConnection;
        let partnerId = null;
        let partnerName = "Stranger";
        let isSearching = false;
        let typingTimeout = null;
        let myName = "";
        let myData = {};
        let isScreenSharing = false;

        // --- 0. LOGIN & STORAGE ---

        function saveProfile(profile) {
            localStorage.setItem(STORAGE_KEY, JSON.stringify(profile));
        }

        function loadProfile() {
            const stored = localStorage.getItem(STORAGE_KEY);
            return stored ? JSON.parse(stored) : null;
        }

        function processLogin(profile) {
            myName = profile.name;
            myData = profile;
            saveProfile(profile);

            // UI Transitions
            loginModal.classList.add('opacity-0', 'pointer-events-none'); // Smooth fade out
            setTimeout(() => loginModal.classList.add('hidden'), 300);
            
            editProfileBtn.classList.remove('hidden');
            addSystemMessage(`Welcome back, ${myName}. Ready to connect.`);
            
            if (socket.connected) {
                socket.emit('join_user', myData);
            }
            startCamera();
        }

        // Auto-login
        window.addEventListener('DOMContentLoaded', () => {
            const savedProfile = loadProfile();
            if (savedProfile) {
                usernameInput.value = savedProfile.name;
                genderInput.value = savedProfile.gender;
                interestInput.value = savedProfile.interest;
                processLogin(savedProfile);
            }
        });

        loginForm.addEventListener('submit', (e) => {
            e.preventDefault();
            const profile = {
                name: usernameInput.value.trim(),
                gender: genderInput.value,
                interest: interestInput.value
            };
            if (profile.name) processLogin(profile);
        });

        editProfileBtn.addEventListener('click', () => {
            loginModal.classList.remove('hidden', 'opacity-0', 'pointer-events-none');
            closeModalBtn.classList.remove('hidden');
        });

        closeModalBtn.addEventListener('click', () => {
            loginModal.classList.add('opacity-0', 'pointer-events-none');
            setTimeout(() => loginModal.classList.add('hidden'), 300);
        });

        // --- 1. MEDIA & SCREEN SHARE ---
        async function startCamera() {
            try {
                if (!localStream) {
                    localStream = await navigator.mediaDevices.getUserMedia({ video: { width: 640 }, audio: true });
                    localVideo.srcObject = localStream;
                }
            } catch (err) {
                alert("Please enable camera access to use this app.");
            }
        }

        async function toggleScreenShare() {
            if (isScreenSharing) {
                // Stop Sharing
                stopScreenShare();
            } else {
                // Start Sharing
                try {
                    screenStream = await navigator.mediaDevices.getDisplayMedia({ video: true });
                    const screenTrack = screenStream.getVideoTracks()[0];
                    
                    if (peerConnection) {
                        const sender = peerConnection.getSenders().find(s => s.track.kind === 'video');
                        if (sender) {
                            sender.replaceTrack(screenTrack);
                        }
                    }
                    
                    // Show screen locally
                    localVideo.srcObject = screenStream;
                    localVideo.classList.remove('mirrored'); // Don't mirror screen
                    isScreenSharing = true;
                    shareScreenBtn.classList.add('bg-red-500', 'hover:bg-red-600');
                    shareScreenBtn.innerHTML = '<i class="fas fa-times-circle"></i>';

                    // Handle system stop button
                    screenTrack.onended = () => {
                        stopScreenShare();
                    };

                } catch (e) {
                    console.error("Screen share cancelled", e);
                }
            }
        }

        function stopScreenShare() {
            if (!isScreenSharing) return;
            
            // Stop screen tracks
            if (screenStream) {
                screenStream.getTracks().forEach(track => track.stop());
            }

            // Revert to camera
            const videoTrack = localStream.getVideoTracks()[0];
            if (peerConnection) {
                const sender = peerConnection.getSenders().find(s => s.track.kind === 'video');
                if (sender) {
                    sender.replaceTrack(videoTrack);
                }
            }
            
            localVideo.srcObject = localStream;
            localVideo.classList.add('mirrored'); // Re-enable mirror for camera
            isScreenSharing = false;
            shareScreenBtn.classList.remove('bg-red-500', 'hover:bg-red-600');
            shareScreenBtn.classList.add('bg-indigo-500/20');
            shareScreenBtn.innerHTML = '<i class="fas fa-desktop"></i>';
        }
        
        toggleMicBtn.addEventListener('click', (e) => {
            e.preventDefault();
            if (!localStream) return;
            const track = localStream.getAudioTracks()[0];
            track.enabled = !track.enabled;
            toggleMicBtn.innerHTML = track.enabled ? '<i class="fas fa-microphone"></i>' : '<i class="fas fa-microphone-slash text-red-400"></i>';
            toggleMicBtn.classList.toggle('bg-red-500/20', !track.enabled);
        });

        toggleCamBtn.addEventListener('click', (e) => {
            e.preventDefault();
            if (!localStream) return;
            const track = localStream.getVideoTracks()[0];
            track.enabled = !track.enabled;
            toggleCamBtn.innerHTML = track.enabled ? '<i class="fas fa-video"></i>' : '<i class="fas fa-video-slash text-red-400"></i>';
            toggleCamBtn.classList.toggle('bg-red-500/20', !track.enabled);
        });

        shareScreenBtn.addEventListener('click', (e) => {
             e.preventDefault();
             toggleScreenShare();
        });

        // --- 2. SOCKET EVENTS ---
        socket.on('connect', () => {
            statusEl.innerText = "Connected";
            statusEl.classList.add('text-emerald-500');
            if (myName) socket.emit('join_user', myData);
        });

        socket.on('disconnect', () => {
            statusEl.innerText = "Reconnecting...";
            statusEl.classList.remove('text-emerald-500');
            statusEl.classList.add('text-amber-500');
        });

        socket.on('user_count', (count) => {
            userCountEl.innerText = `${count} online`;
        });

        socket.on('match_found', (data) => {
            partnerId = data.partner_id;
            partnerName = data.partner_name || "Stranger";
            isSearching = false;
            
            playNotification('match'); // Sound Effect

            // UI Updates
            overlay.classList.add('hidden');
            remotePlaceholder.classList.add('hidden');
            msgInput.disabled = false;
            msgInput.focus();
            document.getElementById('sendBtn').disabled = false;
            
            // Partner Tag
            partnerNameDisplay.innerText = partnerName;
            partnerInfoTag.classList.remove('hidden');

            // --- Show Greeting ---
            greetingName.innerText = partnerName;
            greetingOverlay.classList.remove('hidden');
            // Small delay to allow display:block to apply before opacity transition
            setTimeout(() => {
                greetingOverlay.classList.remove('opacity-0', 'translate-y-4');
            }, 50);

            // Hide after 3 seconds
            setTimeout(() => {
                greetingOverlay.classList.add('opacity-0', 'translate-y-4');
                setTimeout(() => {
                    greetingOverlay.classList.add('hidden');
                }, 700);
            }, 3000);
            
            // Clear default message if it's the only one
            if(chatLog.children.length === 1 && chatLog.children[0].classList.contains('opacity-50')) {
                chatLog.innerHTML = '';
            }
            
            addSystemMessage(`Connected with ${partnerName}. Say Hi!`);
            startWebRTC(data.role === 'offerer');
        });

        socket.on('partner_disconnected', () => {
            closeConnection();
            addSystemMessage(`${partnerName} has left the chat.`, 'error');
            partnerName = "Stranger";
            partnerInfoTag.classList.add('hidden');
            remotePlaceholder.classList.remove('hidden');
            stopScreenShare(); // Reset screen share state
        });

        socket.on('receive_message', (data) => {
            playNotification('message'); // Sound Effect
            addChatMessage(partnerName, data.msg, false);
            typingIndicator.classList.add('hidden');
        });

        socket.on('partner_typing', (data) => {
            typingNameEl.innerText = partnerName;
            data.isTyping ? typingIndicator.classList.remove('hidden') : typingIndicator.classList.add('hidden');
        });

        socket.on('signal', async (data) => {
            if (!peerConnection) return;
            try {
                if (data.type === 'offer') {
                    await peerConnection.setRemoteDescription(new RTCSessionDescription(data.sdp));
                    const answer = await peerConnection.createAnswer();
                    await peerConnection.setLocalDescription(answer);
                    socket.emit('signal', { target: partnerId, type: 'answer', sdp: answer });
                } else if (data.type === 'answer') {
                    await peerConnection.setRemoteDescription(new RTCSessionDescription(data.sdp));
                } else if (data.type === 'candidate' && data.candidate) {
                    await peerConnection.addIceCandidate(new RTCIceCandidate(data.candidate));
                }
            } catch(e) { console.error("Signaling error", e); }
        });

        // --- 3. WebRTC ---
        function startWebRTC(isOfferer) {
            console.log("Starting WebRTC. Offerer:", isOfferer);
            peerConnection = new RTCPeerConnection(peerConnectionConfig);
            
            if (localStream) {
                localStream.getTracks().forEach(track => {
                    peerConnection.addTrack(track, localStream);
                });
            }

            // Handle incoming stream
            peerConnection.ontrack = (event) => {
                console.log("Track received");
                if (remoteVideo.srcObject !== event.streams[0]) {
                    remoteVideo.srcObject = event.streams[0];
                    // FORCE PLAY to fix "cannot see face" issues
                    remoteVideo.play().catch(e => console.error("Error playing video:", e));
                }
            };

            peerConnection.onicecandidate = (event) => {
                if (event.candidate) {
                    socket.emit('signal', { target: partnerId, type: 'candidate', candidate: event.candidate });
                }
            };

            if (isOfferer) {
                 // Moved outside onnegotiationneeded to prevent race conditions
                 createAndSendOffer();
            }
        }
        
        async function createAndSendOffer() {
             try {
                const offer = await peerConnection.createOffer();
                await peerConnection.setLocalDescription(offer);
                socket.emit('signal', { target: partnerId, type: 'offer', sdp: offer });
            } catch (err) { console.error("Offer Error:", err); }
        }

        function closeConnection() {
            if (peerConnection) {
                peerConnection.close();
                peerConnection = null;
            }
            remoteVideo.srcObject = null;
            partnerId = null;
            msgInput.disabled = true;
            document.getElementById('sendBtn').disabled = true;
            typingIndicator.classList.add('hidden');
        }

        // --- 4. INTERACTIONS ---
        function findNewPartner() {
            if (isSearching) return;
            if (partnerId) {
                socket.emit('leave_chat'); 
                closeConnection();
            }
            isSearching = true;
            overlay.classList.remove('hidden');
            remotePlaceholder.classList.remove('hidden');
            partnerInfoTag.classList.add('hidden');
            
            // Clear chat for new session
            chatLog.innerHTML = '';
            
            addSystemMessage("Searching for a partner...");
            socket.emit('find_partner');
        }

        nextBtn.addEventListener('click', findNewPartner);
        stopBtn.addEventListener('click', () => {
            if (partnerId) {
                socket.emit('leave_chat');
                closeConnection();
                addSystemMessage("You stopped the chat.", 'error');
                stopScreenShare();
            }
            isSearching = false;
            overlay.classList.add('hidden');
            socket.emit('leave_queue');
        });

        chatForm.addEventListener('submit', (e) => {
            e.preventDefault();
            const msg = msgInput.value.trim();
            if (msg && partnerId) {
                socket.emit('send_message', { target: partnerId, msg: msg });
                addChatMessage("You", msg, true);
                msgInput.value = '';
                socket.emit('typing', { target: partnerId, isTyping: false });
            }
        });

        msgInput.addEventListener('input', () => {
            if (!partnerId) return;
            socket.emit('typing', { target: partnerId, isTyping: true });
            clearTimeout(typingTimeout);
            typingTimeout = setTimeout(() => socket.emit('typing', { target: partnerId, isTyping: false }), 1000);
        });

        // --- UI HELPERS ---
        function addSystemMessage(text, type='info') {
            const div = document.createElement('div');
            const color = type === 'error' ? 'text-rose-400' : 'text-slate-500';
            div.className = `text-center text-xs font-medium my-3 ${color} uppercase tracking-wider`;
            div.innerHTML = `<span>— ${text} —</span>`;
            chatLog.appendChild(div);
            scrollToBottom();
        }

        function addChatMessage(sender, text, isSelf) {
            const wrapper = document.createElement('div');
            wrapper.className = `flex w-full mb-4 ${isSelf ? 'justify-end' : 'justify-start'}`;
            
            const bubble = document.createElement('div');
            const selfStyle = "bg-indigo-600 text-white rounded-2xl rounded-tr-sm shadow-md shadow-indigo-500/10";
            const partnerStyle = "bg-slate-800 text-slate-200 rounded-2xl rounded-tl-sm shadow-sm border border-slate-700";
            
            bubble.className = `max-w-[85%] px-5 py-3 text-sm leading-relaxed ${isSelf ? selfStyle : partnerStyle}`;
            
            // SECURITY FIX: Use textContent instead of innerHTML to prevent XSS
            bubble.textContent = text; 
            
            wrapper.appendChild(bubble);
            chatLog.appendChild(wrapper);
            scrollToBottom();
        }

        function scrollToBottom() { chatLog.scrollTop = chatLog.scrollHeight; }

        document.addEventListener('keydown', (e) => {
            if (e.key === "Escape") findNewPartner();
        });
    </script>
</body>
</html>