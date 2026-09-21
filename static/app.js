document.addEventListener("DOMContentLoaded", async () => {
    const hudContainer = document.getElementById("hud-container");
    const btnMinToggle = document.getElementById("btn-min-toggle");
    const btnToggleMaps = document.getElementById("btn-toggle-maps");
    const mapChevron = document.getElementById("map-chevron");
    const mapDropdown = document.getElementById("map-dropdown");
    const mapTitle = document.getElementById("map-title");
    const welcomeScreen = document.getElementById("welcome-screen");
    const simStats = document.getElementById("simulation-stats");

    let availableMaps = [];
    let currentMap = null;
    let isStaticMode = false;
    let currentAnimationId = null;
    let currentSimAbortController = null;
    let currentRenderer = null;

    const urlParams = new URLSearchParams(window.location.search);
    const targetMap = urlParams.get('map');
    const rawData = urlParams.get('data');

    if (rawData) {
        try {
            const decodedString = decodeURIComponent(rawData);
            data = reconstruct_data(decodedString);
            
            welcomeScreen.style.display = "none";
            hudContainer.classList.remove("selecting");
            mapTitle.innerText = data.mapName.replace(".txt","");
            
            // Render directly, no extra API calls needed
            initializeThreeJSScene(data, data.rawTimeline);
        } catch (e) {
            console.error("Failed to parse custom URL protocol:", e);
        }
    }

    // Minimize Toggle Logic
    btnMinToggle.addEventListener("click", () => {
        const isMin = hudContainer.classList.toggle("minimized");
        btnMinToggle.innerText = isMin ? "+" : "-";
        if (isMin) mapDropdown.classList.remove("active");
    });

    // Map Selector Dropdown Logic
    btnToggleMaps.addEventListener("click", () => {
        if (hudContainer.classList.contains("minimized")) return;
        hudContainer.classList.toggle("selecting");
    });

    // Fetch maps via API
    try {
        const res = await fetch("/api/maps");
        if (res.ok) {
            availableMaps = await res.json();
            populateMapList();
        } else {
            isStaticMode = true;
            await loadStaticFallback();
        }
    } catch (e) {
        isStaticMode = true;
        await loadStaticFallback();
    }
    
    // Automatically execute the map provided by the CLI
    if (targetMap) {
        selectAndRunMap(targetMap, null);
    }

    function reconstruct_data(rawData) {
        const parts = rawData.split('~');
        const mapName = parts[0].replace(/_/g, ' ');
        const numDrones = parseInt(parts[1], 10);
        // Reconstruct Hubs
        const hubs = {};
        const hubStr = parts[2]; // Remove "hubs:"
        if (hubStr) {
            hubStr.split('/').forEach(h => {
                console.log("hub: " + h);
                const [name, props] = h.split('.');
                const [x, y, flags, color] = props.split('_');
                
                let role = "hub";
                let maxDrones = 1;
                if (flags.includes('s')) { role = "start_hub"; maxDrones = 999999; }
                else if (flags.includes('e')) { role = "end_hub"; maxDrones = 999999; }
                
                let zoneType = "normal";
                if (flags.includes('r')) zoneType = "restricted";
                else if (flags.includes('b')) zoneType = "blocked";
                else if (flags.includes('p')) zoneType = "priority";
                
                const capMatch = flags.match(/\d+/);
                if (capMatch && !flags.includes('s') && !flags.includes('e')) {
                    maxDrones = parseInt(capMatch[0], 10);
                }

                hubs[name] = { 
                    x: parseFloat(x), 
                    y: parseFloat(y), 
                    role, 
                    zone_type: zoneType, 
                    max_drones: maxDrones, 
                    color: color 
                };
            });
        }
        // Reconstruct Connections
        const connections = parts[3].split('.');
        // Reconstruct Timeline
        const rawTimeline = [{}]; 
        const turnsStr = parts[4];
        if (turnsStr) {
            turnsStr.split('/').forEach(turn => {
                const turnMoves = {};
                turn.split('.').forEach(move => {
                    const dashIdx = move.indexOf('-');
                    if(dashIdx !== -1) {
                        turnMoves[move.substring(0, dashIdx)] = move.substring(dashIdx + 1);
                    }
                });
                rawTimeline.push(turnMoves);
            });
        }

        return {
            mapName: mapName,
            drone_number: numDrones,
            hubs: hubs,
            connections: connections,
            rawTimeline: rawTimeline
        };
    }

    function populateMapList() {
        mapDropdown.innerHTML = "";
        availableMaps.forEach(mapName => {
            const div = document.createElement("div");
            div.className = "map-item";
            div.innerText = mapName.replace(".txt", "");
            div.onclick = () => selectAndRunMap(mapName, div);
            mapDropdown.appendChild(div);
        });
    }

    async function loadStaticFallback() {
        try {
            const res = await fetch("data/map-list.json");
            const data = await res.json();
            availableMaps = data.maps;
            populateMapList();
        } catch (e) {
            console.error("No maps available via API or static fallback.");
        }
    }

    async function selectAndRunMap(mapName, element) {
        document.querySelectorAll(".map-item").forEach(
            el => el.classList.remove("selected"));
        if (element) element.classList.add("selected");
        
        currentMap = mapName;
        mapTitle.innerText = mapName.replace(/_/g, " ").replace(".txt", " ");
        mapDropdown.classList.remove("active");
        mapChevron.classList.remove("open");
        
        welcomeScreen.style.opacity = "0";
        setTimeout(() => welcomeScreen.style.display = "none", 500);
        hudContainer.classList.remove("selecting");
        
        let response;
        if (isStaticMode) {
            response = await fetch(`data/maps/${mapName}.data`);
            if (!response.ok) {
                console.error("Server returned an error:", response.status);
                return;
            }
            try {
                response = await response.text();
                const data = reconstruct_data(response);
                welcomeScreen.style.display = "none";
                hudContainer.classList.remove("selecting");
                mapTitle.innerText = data.mapName.replace(".txt","");
                initializeThreeJSScene(data, data.rawTimeline);
            } catch (e) {
                console.error("Failed to parse custom URL protocol:", e);
            }
        } else {
            response = await fetch("/api/simulate", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ map_name: mapName })
            });
            if (!response.ok) {
                console.error("Server returned an error:", response.status);
                return;
            }
            const simData = await response.json();
            initializeThreeJSScene(simData.map_data, simData.timeline);
        }

    }

    function initializeThreeJSScene(mapData, rawTimeline) {
        if (currentAnimationId) {
            cancelAnimationFrame(currentAnimationId);
            currentAnimationId = null;
        }
        if (currentSimAbortController) {
            currentSimAbortController.abort();
        }
        if (currentRenderer) {
            currentRenderer.dispose();
            currentRenderer.forceContextLoss();
        }
        
        currentSimAbortController = new AbortController();
        const signal = currentSimAbortController.signal;
        const existingCanvas = document.querySelector('canvas');
        if (existingCanvas) {
            existingCanvas.remove();
        } 

        if (typeof rawTimeline == "string") {
            rawTimelineString = rawTimeline;
            rawTimeline = [{}]; // Turn 0 is always empty
            if (rawTimelineString) {
                const lines = rawTimelineString.trim().split('\n');
                for (const line of lines) {
                    if (!line || line.startsWith("Numbers")) continue;
                    
                    const turnMoves = {};
                    const moves = line.trim().split(/\s+/);
                    
                    for (const move of moves) {
                        const dashIdx = move.indexOf('-');
                        if (dashIdx !== -1) {
                            const droneId = move.substring(0, dashIdx);
                            const dest = move.substring(dashIdx + 1);
                            turnMoves[droneId] = dest;
                        }
                    }
                    rawTimeline.push(turnMoves);
                }
            }
        }

        const R = 200;

        const PALETTE = {
            "red": 0xff4444, "green": 0x44ff66, "blue": 0x4488ff,
            "yellow": 0xffff33, "orange": 0xff9933, "purple": 0xaa55ff,
            "magenta": 0xff44aa, "cyan": 0x33ffff, "brown": 0xaa7755,
            "black": 0x333333, "gray": 0x999999, "gold": 0xffd700,
            "maroon": 0xaa3333, "darkred": 0xcc2222, "crimson": 0xff3355,
            "lime": 0xaaff33, "default": 0x778899
        };

        let state = {
            isPlaying: false, turn: 0, maxTurns: rawTimeline.length - 1,
            progress: 0.0, speed: 1.0, totalDrones: mapData.drone_number
        };

        const endHub = Object.entries(mapData.hubs).find(
            ([name, h]) => h.role === "end_hub"
        )[0];
        const startHub = Object.entries(mapData.hubs).find(
            ([name, h]) => h.role === "start_hub"
        )[0];
        const hubLookup = {};
        Object.entries(mapData.hubs).forEach(([hub_name, h]) => {
            hubLookup[hub_name.trim()] = h;
        });
        console.log("hubLookup", hubLookup)

        function normalizeName(name) {
            if (!name) return "";
            if(!name.includes('-')) return name;
            const pts = name.split('-');
            return pts[0] < pts[1] ?
                `${pts[0]}-${pts[1]}` : `${pts[1]}-${pts[0]}`;
        }

        let minX = Infinity, maxX = -Infinity;
        let minY = Infinity, maxY = -Infinity;
        Object.values(mapData.hubs).forEach(h => {
            if (h.x < minX) minX = h.x;
            if (h.x > maxX) maxX = h.x;
            if (h.y < minY) minY = h.y;
            if (h.y > maxY) maxY = h.y;
        });

        const centerX = (minX + maxX) / 2;
        const centerY = (minY + maxY) / 2;
        const mapW = Math.max(maxX - minX, 1);
        const mapH = Math.max(maxY - minY, 1);
        const mapMaxDim = Math.max(mapW, mapH);

        const mapScale = 0.6 / Math.max(mapMaxDim, 1);
        const dynScale = Math.max(
            0.15, Math.min(1.0, 10.0 / Math.max(5, mapMaxDim))
        );

        function mapToSphere(x, y, radiusOffset = 0) {
            const planeX = (x - centerX) * mapScale * R;
            const planeZ = (y - centerY) * mapScale * R;
            const vec = new THREE.Vector3(planeX, R, planeZ).normalize();
            return vec.multiplyScalar(R + radiusOffset);
        }

        const droneIds = Array.from(
            {length: mapData.drone_number},
            (_, i) => `D${i+1}`);
        const dronePaths = {};
        
        droneIds.forEach(id => {
            dronePaths[id] = new Array(state.maxTurns + 1).fill(startHub);
        });

        for(let t = 1; t <= state.maxTurns; t++) {
            const moves = rawTimeline[t];
            droneIds.forEach(id => {
                dronePaths[id][t] = moves[id] ? moves[id] : dronePaths[id][t-1];
            });
        }

        function getHubPos(nodeName, radiusOffset) {
            const cleanName = (nodeName || "").trim();
            if (hubLookup[cleanName]) {
                return mapToSphere(
                    hubLookup[cleanName].x, 
                    hubLookup[cleanName].y, 
                    radiusOffset
                );
            }
            return new THREE.Vector3(0, R + radiusOffset, 0); 
        }

        const parsedSteps = {};
        droneIds.forEach(id => {
            parsedSteps[id] = [];
            for(let t = 0; t <= state.maxTurns; t++) {
                let u = dronePaths[id][t];
                let v = dronePaths[id][Math.min(t+1, state.maxTurns)];

                let isUTransit = u.includes('-');
                let isVTransit = v.includes('-');

                let actualStart, actualEnd, movePhase;

                if (!isUTransit && isVTransit) {
                    actualStart = u;
                    const parts = v.split('-');
                    actualEnd = parts.find(n => n !== u) || u;
                    movePhase = 1;
                } else if (isUTransit && !isVTransit) {
                    const parts = u.split('-');
                    actualStart = parts.find(n => n !== v) || v;
                    actualEnd = v;
                    movePhase = 2;
                } else if (isUTransit && isVTransit) {
                    let futureNode = u;
                    for(let ft = t+1; ft <= state.maxTurns; ft++) {
                        if(!dronePaths[id][ft].includes('-')) {
                            futureNode = dronePaths[id][ft];
                            break;
                        }
                    }
                    const parts = u.split('-');
                    actualStart= parts.find(n => n !== futureNode) || parts[0];
                    actualEnd = futureNode !== u ? futureNode : parts[1];
                    movePhase = 3;
                } else {
                    actualStart = u;
                    actualEnd = v;
                    movePhase = 0;
                }

                parsedSteps[id][t] = {
                    p1: getHubPos(actualStart, 0.0),
                    p2: getHubPos(actualEnd, 0.0),
                    movePhase: movePhase,
                    realEndName: actualEnd,
                    startName: actualStart,
                    rawStart: u,
                    rawEnd: v
                };
            }
        });

        const vecCacheA = new THREE.Vector3();
        const vecCacheB = new THREE.Vector3();

        const scene = new THREE.Scene();

        const canvas = document.createElement('canvas');
        canvas.width = 512; canvas.height = 512;
        const ctx = canvas.getContext('2d');
        const grad = ctx.createRadialGradient(256, 256, 0, 256, 256, 256);
        grad.addColorStop(0, '#0a101d');
        grad.addColorStop(1, '#020408');
        ctx.fillStyle = grad;
        ctx.fillRect(0, 0, 512, 512);
        scene.background = new THREE.CanvasTexture(canvas);

        const camera = new THREE.PerspectiveCamera(
            45, window.innerWidth / window.innerHeight, 0.1, 2500
        );
        const renderer = new THREE.WebGLRenderer({
            antialias: true, powerPreference: "high-performance"
        });
        renderer.setSize(window.innerWidth, window.innerHeight);
        renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
        document.body.appendChild(renderer.domElement);
        currentRenderer = renderer;

        const ambientLight = new THREE.AmbientLight(0xffffff, 0.8);
        scene.add(ambientLight);
        const dirLight = new THREE.DirectionalLight(0xffffff, 1.2);
        dirLight.position.set(100, 200, 100);
        scene.add(dirLight);

        const rawSvg = `<svg xmlns="http://www.w3.org/2000/svg"
                            viewBox="0 -200 960 960">
            <style>
                polygon {
                    fill: #ffffff; stroke-width: 0px;
                    filter: drop-shadow(0 0 20px rgba(0,255,255,0.9));
                }
            </style>
            <polygon points="32,412.6 362.1,412.6 362.1,578 526.8,578
                526.8,279.1 197.3,279.1 526.8,-51.1 362.1,-51.1 32,279.1 "/>
            <polygon points="597.9,114.2 762.7,-51.1 597.9,-51.1 "/>
            <polygon points="762.7,114.2 597.9,279.1 597.9,443.9
                762.7,443.9 762.7,279.1 928,114.2 928,-51.1 762.7,-51.1 "/>
            <polygon points="928,279.1 762.7,443.9 928,443.9 "/>
        </svg>`;
        const svgDataUri = 'data:image/svg+xml;utf8,' +
                        encodeURIComponent(rawSvg);

        const textureLoader = new THREE.TextureLoader();
        textureLoader.load(svgDataUri, (texture) => {
            const logoMat = new THREE.MeshBasicMaterial({
                map: texture, transparent: true, opacity: 0.1,
                blending: THREE.NormalBlending, depthWrite: false
            });
            const logoGeo = new THREE.PlaneGeometry(600, 600);
            const logoMesh = new THREE.Mesh(logoGeo, logoMat);
            logoMesh.position.set(0, R - 700, -1200);
            logoMesh.lookAt(0, R + 400, 0);
            scene.add(logoMesh);
        });

        const globeGroup = new THREE.Group();
        const globeGeo = new THREE.SphereGeometry(R, 64, 64);
        const customGlobeMat = new THREE.ShaderMaterial({
            uniforms: {
                colorCenter: { value: new THREE.Color(0x061833) },
                colorEdge: { value: new THREE.Color(0x020408) }
            },
            vertexShader: `
                varying vec3 vNormal;
                void main() {
                    vNormal = normalize(normalMatrix * normal);
                    gl_Position = projectionMatrix * modelViewMatrix *
                                  vec4(position, 1.0);
                }
            `,
            fragmentShader: `
                uniform vec3 colorCenter;
                uniform vec3 colorEdge;
                varying vec3 vNormal;
                void main() {
                    float intensity = pow(
                        abs(dot(vNormal, vec3(0.0, 0.0, 1.0))), 1.5
                    );
                    gl_FragColor = vec4(
                        mix(colorEdge, colorCenter, intensity), 1.0
                    );
                }
            `
        });
        const globeMesh = new THREE.Mesh(globeGeo, customGlobeMat);
        globeMesh.scale.setScalar(0.995);

        const wireMat = new THREE.MeshBasicMaterial({
            color: 0x0f2a55, wireframe: true, transparent: true, opacity: 0.25
        });
        const wireMesh = new THREE.Mesh(globeGeo, wireMat);
        wireMesh.scale.setScalar(1.000);

        globeGroup.add(globeMesh);
        globeGroup.add(wireMesh);
        scene.add(globeGroup);

        const hubObjects = {};
        const connectionMeshes = {};
        const droneMeshes = {};
        const interactables = [];

        function createConcentricHub(colName, colHex, maxDrns, isRstrctd) {
            const group = new THREE.Group();
            const hasHighCap = maxDrns > 1;
            const numElements = hasHighCap ? 4 : 3;

            group.userData = {
                activationLevel: 0.0, pulsePhase: Math.random() * Math.PI * 2,
                numElements: numElements
            };

            let mats = [];
            for (let i = 0; i < numElements; i++) {
                let m = new THREE.MeshStandardMaterial({
                    color: colHex, emissive: colHex, emissiveIntensity: 0.3,
                    transparent: true, opacity: 0.4, side: THREE.DoubleSide
                });
                if (colName === 'rainbow') {
                    const colors = hasHighCap ?
                        [0x33ff66, 0xaaff33, 0xffff33, 0xff3333] :
                        [0x33ff66, 0xffff33, 0xff3333];
                    m.color.setHex(colors[i]);
                    m.emissive.setHex(colors[i]);
                }
                mats.push(m);
            }

            let meshes = [];
            if (isRstrctd) {
                meshes.push(new THREE.Mesh(
                    new THREE.PlaneGeometry(2.4 * dynScale, 0.8 * dynScale),
                    mats[0]
                ));
            } else {
                meshes.push(new THREE.Mesh(
                    new THREE.RingGeometry(0.5 * dynScale, 1.2 * dynScale, 24),
                    mats[0]
                ));
            }

            if (hasHighCap) {
                meshes.push(new THREE.Mesh(
                    new THREE.RingGeometry(1.5 * dynScale, 2.0 * dynScale, 24),
                    mats[1]
                ));
                meshes.push(new THREE.Mesh(
                    new THREE.RingGeometry(2.3 * dynScale, 2.8 * dynScale, 32),
                    mats[2]
                ));
                meshes.push(new THREE.Mesh(
                    new THREE.RingGeometry(3.1 * dynScale, 3.5 * dynScale, 32),
                    mats[3]
                ));
            } else {
                meshes.push(new THREE.Mesh(
                    new THREE.RingGeometry(1.8 * dynScale, 2.5 * dynScale, 24),
                    mats[1]
                ));
                meshes.push(new THREE.Mesh(
                    new THREE.RingGeometry(3.1 * dynScale, 3.5 * dynScale, 32),
                    mats[2]
                ));
            }

            meshes.forEach(m => group.add(m));
            return group;
        }

        Object.entries(mapData.hubs).forEach(([hub_name, hub]) => {
            const colorKey = hub.color ? hub.color.toLowerCase() : "default";
            const colorHex = PALETTE[colorKey] || PALETTE["default"];

            // Implement defaults stripped from the JSON payload
            const maxDrones = hub.max_drones !== undefined ? hub.max_drones : 1;
            const role = hub.role || "hub";
            const zoneType = hub.zone_type || "normal";
            const isRestricted = zoneType.toLowerCase().includes("restricted");

            const group = createConcentricHub(
                colorKey, colorHex, maxDrones, isRestricted
            );
            const pos = mapToSphere(hub.x, hub.y, 1.2);
            group.position.copy(pos);
            group.up.set(0, 0, 1);
            group.lookAt(pos.clone().multiplyScalar(2));

            const hitMat = new THREE.MeshBasicMaterial({
                transparent: true, opacity: 0, depthWrite: false
            });
            const hitGeo = new THREE.SphereGeometry(4.0 * dynScale, 8, 8);
            const hitMesh = new THREE.Mesh(hitGeo, hitMat);

            hitMesh.userData = { type: 'hub', 
                data: hub, name: hub_name, group: group,
                role, zoneType, maxDrones };
            group.add(hitMesh);

            scene.add(group);
            interactables.push(hitMesh);
            hubObjects[hub_name] = group;
        });

        const tubeMat = new THREE.MeshStandardMaterial({
            color: 0xffffff, emissive: 0xffffff, transparent: true,
            opacity: 0.08, emissiveIntensity: 0.1
        });

        mapData.connections.forEach(connName => {
            const parts = connName.split('-');
            const h1 = mapData.hubs[parts[0]];
            const h2 = mapData.hubs[parts[1]];
            if(!h1 || !h2) return;

            const p1 = mapToSphere(h1.x, h1.y, 0.1);
            const p2 = mapToSphere(h2.x, h2.y, 0.1);
            const dist = p1.distanceTo(p2);

            const mid = p1.clone().add(p2).normalize().multiplyScalar(
                R + 0.1 + dist * 0.02
            );
            const curve = new THREE.QuadraticBezierCurve3(p1, mid, p2);
            const tubeGeo = new THREE.TubeGeometry(
                curve, 16, 0.2 * dynScale, 6, false
            );

            const tubeMesh = new THREE.Mesh(tubeGeo, tubeMat.clone());
            const normName = normalizeName(connName);

            connectionMeshes[normName] = tubeMesh;
            scene.add(tubeMesh);
        });

        function createDroneGroup() {
            const group = new THREE.Group();
            const bGeo = new THREE.BoxGeometry(2.0, 0.5, 2.0);
            const bMat = new THREE.MeshStandardMaterial({
                color: 0xeef2f5, metalness: 0.4, roughness: 0.6
            });
            const body = new THREE.Mesh(bGeo, bMat);
            group.add(body);

            const rGeo = new THREE.CylinderGeometry(0.5, 0.5, 0.15, 12);
            const rMat = new THREE.MeshStandardMaterial({
                color: 0xc5d5e5, metalness: 0.5, roughness: 0.4
            });
            const offsets = [
                [1.2, 1.2], [1.2, -1.2], [-1.2, 1.2], [-1.2, -1.2]
            ];

            offsets.forEach(off => {
                const rotor = new THREE.Mesh(rGeo, rMat);
                rotor.position.set(off[0], 0.3, off[1]);
                group.add(rotor);
            });

            group.scale.setScalar(dynScale * 0.9);
            return group;
        }

        droneIds.forEach((id) => {
            const group = createDroneGroup();
            group.userData = { type: 'drone', id: id };
            scene.add(group);
            interactables.push(group.children[0]);
            group.children[0].userData = group.userData;

            droneMeshes[id] = group;

            const startPos = mapToSphere(
                mapData.hubs[startHub].x,
                mapData.hubs[startHub].y,
                1.5
            );
            group.position.copy(startPos);
            group.up.copy(startPos).normalize();
            group.lookAt(startPos.clone().multiplyScalar(2));
        });

        let camYaw = 0;
        let zoomLevel = 0.40;
        const targetZoom = { value: 0.50 };
        let introAnimationActive = true;

        function updateCamera() {
            if (introAnimationActive) {
                zoomLevel += (targetZoom.value - zoomLevel) * 0.18;
                if (Math.abs(zoomLevel - targetZoom.value) < 0.01) {
                    introAnimationActive = false;
                    state.isPlaying = true;
                }
            } else {
                zoomLevel += (targetZoom.value - zoomLevel) * 0.1;
            }

            const polarDist = 180 * zoomLevel + 40 * (1 - zoomLevel);
            const elevation = (Math.PI / 2) * zoomLevel +
                              (Math.PI / 6) * (1 - zoomLevel);

            const cx = polarDist * Math.cos(elevation) * Math.sin(camYaw);
            const cy = R + polarDist * Math.sin(elevation);
            const cz = polarDist * Math.cos(elevation) * Math.cos(camYaw);

            camera.position.set(cx, cy, cz);
            const lookOffset = 30 * (1 - zoomLevel);
            camera.lookAt(0, R, -lookOffset);
        }

        let isDragging = false;
        let previousMouseX = 0;

        window.addEventListener('mousedown', (e) => {
            if(e.target.tagName !== 'CANVAS') return;
            isDragging = true;
            previousMouseX = e.clientX;
        }, { signal });
        window.addEventListener('mouseup', () => isDragging = false, { signal });
        window.addEventListener('mousemove', (e) => {
            if(isDragging) {
                const deltaX = e.clientX - previousMouseX;
                camYaw -= deltaX * 0.005;
                previousMouseX = e.clientX;
            }
        }, { signal });

        window.addEventListener('wheel', (e) => {
            if(e.target.tagName !== 'CANVAS') return;
            introAnimationActive = false;
            targetZoom.value -= e.deltaY * 0.001;
            targetZoom.value = Math.max(0.0, Math.min(1.0, targetZoom.value));
        }, { signal });

        const raycaster = new THREE.Raycaster();
        const mouse = new THREE.Vector2();
        const tooltip = document.getElementById('tooltip');
        let hoveredObject = null;

        window.addEventListener('mousemove', (e) => {
            if(e.target.tagName !== 'CANVAS') return;
            mouse.x = (e.clientX / window.innerWidth) * 2 - 1;
            mouse.y = -(e.clientY / window.innerHeight) * 2 + 1;

            raycaster.setFromCamera(mouse, camera);
            const intersects = raycaster.intersectObjects(interactables);

            if(intersects.length > 0) {
                document.body.style.cursor = 'pointer';
                const hit = intersects[0].object;
                if(hit !== hoveredObject) {
                    hoveredObject = hit;
                }
            } else {
                document.body.style.cursor = 'default';
                hoveredObject = null;
            }
        }, { signal });

        window.addEventListener('click', (e) => {
            if(e.target.tagName !== 'CANVAS') return;
            mouse.x = (e.clientX / window.innerWidth) * 2 - 1;
            mouse.y = -(e.clientY / window.innerHeight) * 2 + 1;

            raycaster.setFromCamera(mouse, camera);
            const intersects = raycaster.intersectObjects(interactables);

            if(intersects.length > 0) {
                const obj = intersects[0].object;
                tooltip.style.left = e.clientX + 'px';
                tooltip.style.top = e.clientY + 'px';
                tooltip.style.display = 'block';

                if(obj.userData.type === 'hub') {
                    const h = obj.userData;
                    const mx = h.maxDrones > 9000 ? '∞' : h.maxDrones;
                    tooltip.innerHTML = `<div class="tooltip-title">
                        ${h.name}</div>Zone: ${h.zoneType}<br>
                        Max Cap: ${mx}`;
                } else if(obj.userData.type === 'drone') {
                    tooltip.innerHTML = `<div class="tooltip-title">
                        Drone ${obj.userData.id}</div>`;
                }
            } else {
                tooltip.style.display = 'none';
            }
        }, { signal });

        function applyFlightPos(mesh, step, progress) {
            let moveProgress = Math.min(1.0, progress);
            let t = 0;

            if (step.movePhase === 0) {
                t = moveProgress;
            } else if (step.movePhase === 1) {
                t = moveProgress * 0.6;
            } else if (step.movePhase === 2) {
                t = 0.6 + (moveProgress * 0.4);
            } else if (step.movePhase === 3) {
                t = 0.6;
            }

            vecCacheA.copy(step.p1).lerp(step.p2, t).normalize();
            const dist = step.p1.distanceTo(step.p2);
            const arcHeight = Math.sin(t * Math.PI) * (dist * 0.4);

            const currentAltitude = R + 1.5 + arcHeight;

            mesh.position.copy(vecCacheA).multiplyScalar(currentAltitude);
            mesh.up.copy(vecCacheA);

            if (moveProgress < 1.0 &&
                step.p1.distanceToSquared(step.p2) > 0.01) {
                vecCacheB.copy(step.p1).lerp(
                    step.p2, Math.min(1.0, t + 0.05)
                ).normalize().multiplyScalar(currentAltitude);
                mesh.lookAt(vecCacheB);
                mesh.rotateX(Math.PI / 15);
            } else {
                vecCacheB.copy(step.p2).normalize().multiplyScalar(
                    currentAltitude
                );
                mesh.lookAt(vecCacheB);
            }
        }

        const elTurn = document.getElementById('val-turn');
        const elDelivered = document.getElementById('val-delivered');
        const elBtnPP = document.getElementById('btn-playpause');
        const elBtnStop = document.getElementById('btn-stop');
        const elBtnBack = document.getElementById('btn-back');
        const elBtnFwd = document.getElementById('btn-forward');

        let lastUIState = "";

        function updateUI(deliveredCount) {
            const currentState = (
                `${state.turn}-${deliveredCount}-${state.isPlaying}`
            );
            if (currentState === lastUIState) return;

            elTurn.innerText = `${state.turn} / ${state.maxTurns}`;
            elDelivered.innerText = (
                `${deliveredCount} / ${state.totalDrones}`
            );
            elBtnPP.innerText = state.isPlaying ? '⏸' : '▶';

            const isStopped = !state.isPlaying && (
                state.turn === 0 || state.turn >= state.maxTurns
            );
            elBtnBack.disabled = isStopped;
            elBtnFwd.disabled = isStopped;

            lastUIState = currentState;
        }

        const clock = new THREE.Clock();

        function animate() {
            currentAnimationId = requestAnimationFrame(animate);
            const delta = clock.getDelta();

            updateCamera();

            if (state.isPlaying) {
                state.progress += (delta * state.speed);

                if (state.progress >= 1.3) {
                    state.progress = 0.0;
                    if (state.turn < state.maxTurns) {
                        state.turn++;
                    } else {
                        state.isPlaying = false;
                        state.progress = 1.3;
                    }
                }
            }

            let deliveredCount = 0;
            const tSafe = Math.min(state.turn, state.maxTurns);

            const activeNodes = new Set();
            const activeConnections = new Set();
            const subtleConnections = new Set();

            droneIds.forEach((id) => {
                const step = parsedSteps[id][tSafe];

                if (step.startName === endHub) {
                    deliveredCount++;
                } else if (
                    step.realEndName === endHub && state.progress >= 1.0
                ) {
                    deliveredCount++;
                }

                const currentLogicalNode = (state.progress >= 1.0) ?
                    dronePaths[id][Math.min(tSafe + 1, state.maxTurns)] :
                    step.rawStart;
                activeNodes.add(normalizeName(currentLogicalNode));

                const isFlying = state.progress > 0.0 && state.progress < 1.0;

                if (step.rawStart.includes('-') || step.rawEnd.includes('-')){
                    const connName = step.rawStart.includes('-') ?
                        step.rawStart : step.rawEnd;

                    if (isFlying || currentLogicalNode.includes('-')) {
                        activeConnections.add(normalizeName(connName));
                        activeNodes.add(normalizeName(step.realEndName));
                    }
                } else if (step.startName !== step.realEndName) {
                    if (isFlying) {
                        const sn = step.startName;
                        const en = step.realEndName;
                        subtleConnections.add(normalizeName(`${sn}-${en}`));
                    }
                }

                const mesh = droneMeshes[id];
                applyFlightPos(mesh, step, state.progress);
            });

            Object.entries(mapData.hubs).forEach(([hub_name, h]) => {
                const hg = hubObjects[hub_name];
                const isActive = activeNodes.has(normalizeName(hub_name));
                const isHovered = hoveredObject &&
                    hoveredObject.userData.type === 'hub' &&
                    hoveredObject.userData.data.name === hub_name;

                const tgtAct = (isActive || isHovered) ? 1.0 : 0.0;
                const spd = delta * 6.0;
                hg.userData.activationLevel += (
                    (tgtAct - hg.userData.activationLevel) * spd
                );

                hg.userData.pulsePhase += delta * 2.5;
                const pulse = (Math.sin(hg.userData.pulsePhase) * 0.5 + 0.5);

                let ringIndex = 0;
                const numElems = hg.userData.numElements;

                hg.children.forEach(c => {
                    if (
                        c.geometry &&
                        (c.geometry.type === 'RingGeometry' ||
                         c.geometry.type === 'PlaneGeometry')
                    ) {
                        const offset = (
                            ringIndex / Math.max(1, numElems - 1)
                        ) * 0.5;
                        const baseAct = hg.userData.activationLevel - offset;
                        let ringAct = Math.max(0, Math.min(1, baseAct * 2.0));

                        if (c.material && c.material.opacity !== undefined) {
                            c.material.opacity = 0.4 + (0.4 * ringAct);
                            c.material.emissiveIntensity = 0.3 +
                                (ringAct * 0.3) + (ringAct * pulse * 0.3);
                        }
                        ringIndex++;
                    }
                });
            });

            mapData.connections.forEach(connName => {
                const normName = normalizeName(connName);
                const tm = connectionMeshes[normName];

                if (tm) {
                    const isActive = activeConnections.has(normName);
                    const isSubtle = subtleConnections.has(normName);

                    let targetOpacity = 0.08;
                    let targetEmissive = 0.1;

                    if (isActive) {
                        targetOpacity = 0.7;
                        targetEmissive = 0.8;
                    } else if (isSubtle) {
                        targetOpacity = 0.4;
                        targetEmissive = 0.4;
                    }

                    const spd = delta * 8.0;
                    tm.material.opacity += (
                        (targetOpacity - tm.material.opacity) * spd
                    );
                    tm.material.emissiveIntensity += (
                        (targetEmissive - tm.material.emissiveIntensity) * spd
                    );
                }
            });

            updateUI(deliveredCount);
            renderer.render(scene, camera);
        }

        const speedInd = document.getElementById('speed-indicator');
        let speedTimeout;
        function showSpeed(text) {
            speedInd.innerText = text;
            speedInd.style.opacity = 1;
            clearTimeout(speedTimeout);
            speedTimeout = setTimeout(() => speedInd.style.opacity = 0, 1000);
        }

        elBtnPP.addEventListener('click', () => {
            introAnimationActive = false;
            state.isPlaying = !state.isPlaying;
            state.speed = 1.0;
            if(state.isPlaying && state.turn === state.maxTurns) {
                state.turn = 0;
                state.progress = 0;
            }
            tooltip.style.display = 'none';
        }, { signal });

        elBtnStop.addEventListener('click', () => {
            introAnimationActive = false;
            state.isPlaying = false;
            state.turn = 0;
            state.progress = 0;
            state.speed = 1.0;
            updateUI(0);
        }, { signal });

        elBtnFwd.addEventListener('click', () => {
            introAnimationActive = false;
            if(state.isPlaying) {
                state.speed = Math.min(state.speed + 4.0, 4.0);
                showSpeed(state.speed.toFixed(1) + 'x Speed');
            } else {
                if(state.turn < state.maxTurns) state.turn++;
                state.progress = 0;
            }
        }, { signal });

        elBtnBack.addEventListener('click', () => {
            introAnimationActive = false;
            if(state.isPlaying) {
                state.speed = Math.max(state.speed - 0.5, 0.5);
                showSpeed(state.speed.toFixed(1) + 'x Speed');
            } else {
                if(state.turn > 0) state.turn--;
                state.progress = 0;
            }
        }, { signal });

        window.addEventListener('resize', () => {
            camera.aspect = window.innerWidth / window.innerHeight;
            camera.updateProjectionMatrix();
            renderer.setSize(window.innerWidth, window.innerHeight);
        }, { signal });

        animate();
    }
});