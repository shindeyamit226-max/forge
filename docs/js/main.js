/* ============================================================
   FORGE — Landing Page JavaScript
   Particles, animations, terminal demo, interactions
   ============================================================ */

// ============================================================
// PARTICLES BACKGROUND
// ============================================================
(function initParticles() {
    const canvas = document.getElementById('particles');
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    let particles = [];
    let animationId;

    function resize() {
        canvas.width = window.innerWidth;
        canvas.height = window.innerHeight;
    }

    function createParticle() {
        return {
            x: Math.random() * canvas.width,
            y: Math.random() * canvas.height,
            vx: (Math.random() - 0.5) * 0.5,
            vy: (Math.random() - 0.5) * 0.5,
            radius: Math.random() * 1.5 + 0.5,
            opacity: Math.random() * 0.3 + 0.1,
        };
    }

    function init() {
        resize();
        particles = [];
        const count = Math.min(80, Math.floor(canvas.width * canvas.height / 15000));
        for (let i = 0; i < count; i++) {
            particles.push(createParticle());
        }
    }

    function draw() {
        ctx.clearRect(0, 0, canvas.width, canvas.height);

        particles.forEach(p => {
            ctx.beginPath();
            ctx.arc(p.x, p.y, p.radius, 0, Math.PI * 2);
            ctx.fillStyle = `rgba(249, 115, 22, ${p.opacity})`;
            ctx.fill();

            p.x += p.vx;
            p.y += p.vy;

            if (p.x < 0 || p.x > canvas.width) p.vx *= -1;
            if (p.y < 0 || p.y > canvas.height) p.vy *= -1;
        });

        // Draw connections
        for (let i = 0; i < particles.length; i++) {
            for (let j = i + 1; j < particles.length; j++) {
                const dx = particles[i].x - particles[j].x;
                const dy = particles[i].y - particles[j].y;
                const dist = Math.sqrt(dx * dx + dy * dy);

                if (dist < 150) {
                    ctx.beginPath();
                    ctx.moveTo(particles[i].x, particles[i].y);
                    ctx.lineTo(particles[j].x, particles[j].y);
                    ctx.strokeStyle = `rgba(249, 115, 22, ${0.05 * (1 - dist / 150)})`;
                    ctx.lineWidth = 0.5;
                    ctx.stroke();
                }
            }
        }

        animationId = requestAnimationFrame(draw);
    }

    window.addEventListener('resize', () => {
        cancelAnimationFrame(animationId);
        init();
        draw();
    });

    init();
    draw();
})();

// ============================================================
// NAVBAR SCROLL EFFECT
// ============================================================
const navbar = document.getElementById('navbar');
window.addEventListener('scroll', () => {
    if (window.scrollY > 50) {
        navbar.classList.add('scrolled');
    } else {
        navbar.classList.remove('scrolled');
    }
});

// ============================================================
// MOBILE MENU
// ============================================================
const mobileToggle = document.getElementById('mobileToggle');
const navLinks = document.querySelector('.nav-links');
if (mobileToggle) {
    mobileToggle.addEventListener('click', () => {
        navLinks.classList.toggle('active');
    });
}

// ============================================================
// SMOOTH SCROLL
// ============================================================
document.querySelectorAll('a[href^="#"]').forEach(anchor => {
    anchor.addEventListener('click', function (e) {
        e.preventDefault();
        const target = document.querySelector(this.getAttribute('href'));
        if (target) {
            target.scrollIntoView({ behavior: 'smooth', block: 'start' });
            // Close mobile menu
            if (navLinks) navLinks.classList.remove('active');
        }
    });
});

// ============================================================
// COUNTER ANIMATION
// ============================================================
function animateCounters() {
    const counters = document.querySelectorAll('.stat-number');
    counters.forEach(counter => {
        const target = parseInt(counter.getAttribute('data-count'));
        const duration = 2000;
        const start = performance.now();

        function update(currentTime) {
            const elapsed = currentTime - start;
            const progress = Math.min(elapsed / duration, 1);
            // Ease out cubic
            const eased = 1 - Math.pow(1 - progress, 3);
            counter.textContent = Math.floor(eased * target).toLocaleString();

            if (progress < 1) {
                requestAnimationFrame(update);
            } else {
                counter.textContent = target.toLocaleString();
            }
        }

        requestAnimationFrame(update);
    });
}

// Trigger counters when hero is visible
const heroObserver = new IntersectionObserver((entries) => {
    entries.forEach(entry => {
        if (entry.isIntersecting) {
            animateCounters();
            heroObserver.disconnect();
        }
    });
}, { threshold: 0.3 });

const heroStats = document.querySelector('.hero-stats');
if (heroStats) heroObserver.observe(heroStats);

// ============================================================
// TERMINAL DEMO
// ============================================================
const terminalDemo = document.getElementById('terminalDemo');
const typedCommand = document.getElementById('typedCommand');

const demoSteps = [
    { type: 'input', text: 'Add rate limiting to all API endpoints' },
    { type: 'thinking', text: '🧠 Understanding task...\n📊 Analyzing codebase with knowledge graph...\n⚡ Found 12 API endpoints in src/routes/' },
    { type: 'action', text: '⚡ graph_impact("api_routes")\n  → Risk: MEDIUM (12 endpoints affected)' },
    { type: 'action', text: '⚡ read("src/middleware/rate_limit.py")' },
    { type: 'action', text: '⚡ write("src/middleware/rate_limit.py", ...)' },
    { type: 'action', text: '⚡ edit("src/routes/auth.py", ...)' },
    { type: 'action', text: '⚡ edit("src/routes/users.py", ...)' },
    { type: 'action', text: '⚡ test()\n  ✅ 24 tests passed' },
    { type: 'response', text: '✅ Done! Added rate limiting to all 12 API endpoints.\n   • Token bucket algorithm (100 req/min)\n   • Applied to: auth, users, items, payments, webhooks\n   • All tests passing' },
];

let demoStepIndex = 0;
let demoCharIndex = 0;
let demoCurrentStep = null;
let demoStarted = false;

function typeDemo() {
    if (!typedCommand || !terminalDemo) return;

    if (demoStepIndex >= demoSteps.length) {
        // Reset after delay
        setTimeout(() => {
            terminalDemo.innerHTML = `<div class="terminal-line"><span class="prompt">You:</span> <span class="typed-text" id="typedCommand"></span><span class="cursor">▌</span></div>`;
            demoStepIndex = 0;
            demoCharIndex = 0;
            demoStarted = false;
            setTimeout(startDemo, 2000);
        }, 5000);
        return;
    }

    demoCurrentStep = demoSteps[demoStepIndex];

    if (demoCurrentStep.type === 'input') {
        if (demoCharIndex < demoCurrentStep.text.length) {
            typedCommand.textContent += demoCurrentStep.text[demoCharIndex];
            demoCharIndex++;
            setTimeout(typeDemo, 30 + Math.random() * 50);
        } else {
            demoStepIndex++;
            demoCharIndex = 0;
            setTimeout(typeDemo, 800);
        }
    } else {
        const div = document.createElement('div');
        div.className = demoCurrentStep.type === 'response' ? 'terminal-response' :
                        demoCurrentStep.type === 'thinking' ? 'terminal-thinking' : 'terminal-action';
        div.style.color = demoCurrentStep.type === 'response' ? '#22c55e' :
                          demoCurrentStep.type === 'thinking' ? '#71717a' : '#06b6d4';
        div.style.marginTop = '8px';
        div.style.whiteSpace = 'pre-wrap';
        terminalDemo.appendChild(div);

        // Type out the response
        let charIdx = 0;
        function typeChar() {
            if (charIdx < demoCurrentStep.text.length) {
                div.textContent += demoCurrentStep.text[charIdx];
                charIdx++;
                setTimeout(typeChar, 10);
            } else {
                demoStepIndex++;
                setTimeout(typeDemo, 600);
            }
        }
        typeChar();
    }
}

function startDemo() {
    if (demoStarted) return;
    demoStarted = true;
    setTimeout(typeDemo, 1000);
}

// Start demo when visible
const demoObserver = new IntersectionObserver((entries) => {
    entries.forEach(entry => {
        if (entry.isIntersecting) {
            startDemo();
            demoObserver.disconnect();
        }
    });
}, { threshold: 0.3 });

if (terminalDemo) demoObserver.observe(terminalDemo);

// ============================================================
// COPY CODE
// ============================================================
function copyCode(btn) {
    const codeBlock = btn.parentElement.querySelector('code');
    if (codeBlock) {
        navigator.clipboard.writeText(codeBlock.textContent).then(() => {
            btn.textContent = 'Copied!';
            btn.style.background = 'var(--green)';
            btn.style.borderColor = 'var(--green)';
            setTimeout(() => {
                btn.textContent = 'Copy';
                btn.style.background = '';
                btn.style.borderColor = '';
            }, 2000);
        });
    }
}

// ============================================================
// SCROLL ANIMATIONS
// ============================================================
const animateOnScroll = new IntersectionObserver((entries) => {
    entries.forEach(entry => {
        if (entry.isIntersecting) {
            const delay = entry.target.getAttribute('data-delay') || 0;
            setTimeout(() => {
                entry.target.style.opacity = '1';
                entry.target.style.transform = 'translateY(0)';
            }, parseInt(delay));
        }
    });
}, { threshold: 0.1 });

document.querySelectorAll('[data-aos]').forEach(el => {
    el.style.opacity = '0';
    el.style.transform = 'translateY(30px)';
    el.style.transition = 'all 0.6s ease';
    animateOnScroll.observe(el);
});

// ============================================================
// KEYBOARD SHORTCUTS
// ============================================================
document.addEventListener('keydown', (e) => {
    // Ctrl+K to focus search (future)
    if (e.ctrlKey && e.key === 'k') {
        e.preventDefault();
    }
});

console.log('%c🔨 Forge', 'font-size: 24px; font-weight: bold; color: #f97316;');
console.log('%cThe Agentic Coding Tool That Actually Works', 'font-size: 14px; color: #a1a1aa;');
console.log('%chttps://github.com/shindeyamit226-max/forge', 'font-size: 12px; color: #3b82f6;');
