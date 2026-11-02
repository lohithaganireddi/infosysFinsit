document.addEventListener('DOMContentLoaded', () => {
  const currencySymbol = window.DEFAULT_CURRENCY || '₹';
  
  // ==========================================================================
  // Number Count-Up and Animation Utilities
  // ==========================================================================
  const animateElements = document.querySelectorAll('.animate-number');
  animateElements.forEach(el => {
    const target = parseFloat(el.getAttribute('data-target'));
    const prefix = el.getAttribute('data-prefix') || '';
    const suffix = el.getAttribute('data-suffix') || '';
    const decimals = el.getAttribute('data-decimals') !== null ? parseInt(el.getAttribute('data-decimals')) : 2;
    
    let startTimestamp = null;
    const duration = 1200; // 1.2 seconds duration
    
    const step = (timestamp) => {
      if (!startTimestamp) startTimestamp = timestamp;
      const progress = Math.min((timestamp - startTimestamp) / duration, 1);
      const ease = 1 - Math.pow(1 - progress, 4); // Quartic ease out
      const currentValue = ease * target;
      
      el.textContent = prefix + currentValue.toLocaleString('en-US', {
        minimumFractionDigits: decimals,
        maximumFractionDigits: decimals
      }) + suffix;
      
      if (progress < 1) {
        window.requestAnimationFrame(step);
      }
    };
    
    setTimeout(() => {
      window.requestAnimationFrame(step);
    }, 100);
  });

  // Animate Circular Health Ring SVG
  const ringFill = document.getElementById('healthRingFill');
  if (ringFill) {
    const score = parseFloat(ringFill.getAttribute('data-score') || '0');
    const circumference = 283;
    const offset = circumference - (circumference * Math.min(100, Math.max(0, score)) / 100);
    setTimeout(() => {
      ringFill.style.strokeDashoffset = offset;
    }, 250);
  }

  // Respect prefers-reduced-motion for background blob animations
  if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
    document.querySelectorAll('.blur-blob').forEach(blob => {
      blob.style.animation = 'none';
      blob.style.transform = 'none';
    });
    document.querySelectorAll('.particle').forEach(p => {
      p.style.animation = 'none';
    });
  }

  // Flash alert dismiss handlers (close button)
  document.querySelectorAll('.flash-close-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      const alert = btn.closest('.flash-alert');
      if (alert) {
        alert.style.transition = 'opacity 0.3s ease, transform 0.3s ease';
        alert.style.opacity = '0';
        alert.style.transform = 'translateY(-8px)';
        setTimeout(() => alert.remove(), 320);
      }
    });
  });

  // ==========================================================================
  // Password Visibility Toggle
  // ==========================================================================
  const passwordToggle = document.getElementById('passwordToggle');
  const passwordInput = document.getElementById('password');
  
  if (passwordToggle && passwordInput) {
    const eyeIcon = passwordToggle.querySelector('.icon-eye');
    const eyeOffIcon = passwordToggle.querySelector('.icon-eye-off');
    passwordToggle.setAttribute('aria-pressed', 'false');
    
    passwordToggle.addEventListener('click', () => {
      const isPassword = passwordInput.getAttribute('type') === 'password';
      passwordInput.setAttribute('type', isPassword ? 'text' : 'password');
      passwordToggle.setAttribute('aria-pressed', isPassword ? 'true' : 'false');
      
      if (isPassword) {
        if (eyeIcon) eyeIcon.style.display = 'none';
        if (eyeOffIcon) eyeOffIcon.style.display = 'block';
      } else {
        if (eyeIcon) eyeIcon.style.display = 'block';
        if (eyeOffIcon) eyeOffIcon.style.display = 'none';
      }
    });
  }

  // Password Confirm Toggle (in Registration)
  const confirmToggle = document.getElementById('confirmToggle');
  const confirmInput = document.getElementById('confirm_password');
  
  if (confirmToggle && confirmInput) {
    const eyeIcon = confirmToggle.querySelector('.icon-eye');
    const eyeOffIcon = confirmToggle.querySelector('.icon-eye-off');
    confirmToggle.setAttribute('aria-pressed', 'false');
    
    confirmToggle.addEventListener('click', () => {
      const isPassword = confirmInput.getAttribute('type') === 'password';
      confirmInput.setAttribute('type', isPassword ? 'text' : 'password');
      confirmToggle.setAttribute('aria-pressed', isPassword ? 'true' : 'false');
      
      if (isPassword) {
        if (eyeIcon) eyeIcon.style.display = 'none';
        if (eyeOffIcon) eyeOffIcon.style.display = 'block';
      } else {
        if (eyeIcon) eyeIcon.style.display = 'block';
        if (eyeOffIcon) eyeOffIcon.style.display = 'none';
      }
    });
  }

  // ==========================================================================
  // Live Password Strength Check & Indicator Updates
  // ==========================================================================
  if (passwordInput) {
    const strengthFill = document.getElementById('strengthFill');
    const strengthValue = document.getElementById('strengthValue');
    
    // Requirements lists
    const reqLength = document.getElementById('req-length');
    const reqUpper = document.getElementById('req-upper');
    const reqLower = document.getElementById('req-lower');
    const reqNumber = document.getElementById('req-number');
    const reqSpecial = document.getElementById('req-special');
    
    passwordInput.addEventListener('input', () => {
      const val = passwordInput.value;
      
      // Test regex checks
      const hasLength = val.length >= 8;
      const hasUpper = /[A-Z]/.test(val);
      const hasLower = /[a-z]/.test(val);
      const hasNumber = /[0-9]/.test(val);
      const hasSpecial = /[^A-Za-z0-9]/.test(val);
      
      // Update requirements checkboxes UI
      updateReqStatus(reqLength, hasLength);
      updateReqStatus(reqUpper, hasUpper);
      updateReqStatus(reqLower, hasLower);
      updateReqStatus(reqNumber, hasNumber);
      updateReqStatus(reqSpecial, hasSpecial);
      
      // Calculate scores
      let score = 0;
      if (val.length > 0) {
        if (hasLength) score += 1;
        if (hasUpper) score += 1;
        if (hasLower) score += 1;
        if (hasNumber) score += 1;
        if (hasSpecial) score += 1;
      }
      
      // Update UI bar fill
      if (strengthFill && strengthValue) {
        let pct = (score / 5) * 100;
        strengthFill.style.width = `${pct}%`;
        
        if (score === 0) {
          strengthValue.textContent = 'None';
          strengthFill.style.backgroundColor = 'transparent';
        } else if (score <= 2) {
          strengthValue.textContent = 'Weak';
          strengthFill.style.backgroundColor = '#EF4444'; // Error red
        } else if (score <= 4) {
          strengthValue.textContent = 'Medium';
          strengthFill.style.backgroundColor = '#F59E0B'; // Warning amber
        } else {
          strengthValue.textContent = 'Strong';
          strengthFill.style.backgroundColor = '#22C55E'; // Success green
        }
      }
    });
  }

  function updateReqStatus(element, isValid) {
    if (!element) return;
    if (isValid) {
      element.classList.add('valid');
      const icon = element.querySelector('svg');
      if (icon) {
        // Swap to check icon
        icon.innerHTML = '<polyline points="20 6 9 17 4 12"></polyline>';
      }
    } else {
      element.classList.remove('valid');
      const icon = element.querySelector('svg');
      if (icon) {
        // Swap to circle icon
        icon.innerHTML = '<circle cx="12" cy="12" r="10"></circle>';
      }
    }
  }

  // ==========================================================================
  // Custom File Upload & Avatar Preview
  // ==========================================================================
  const fileInput = document.getElementById('profileImageInput');
  const avatarPreview = document.getElementById('avatarPreview');
  const uploadBtnText = document.getElementById('uploadBtnText');
  const registerName = document.getElementById('fullname');

  if (fileInput && avatarPreview) {
    fileInput.addEventListener('change', (e) => {
      const file = e.target.files[0];
      if (!file) return;
      
      // Extension limit verification
      const allowedExts = ['png', 'jpg', 'jpeg', 'gif'];
      const fileExt = file.name.split('.').pop().toLowerCase();
      if (!allowedExts.includes(fileExt)) {
        alert('Allowed formats: PNG, JPG, JPEG, GIF');
        fileInput.value = '';
        return;
      }

      // Check size (2MB limit)
      if (file.size > 2 * 1024 * 1024) {
        alert('File size exceeds the 2MB limit.');
        fileInput.value = '';
        return;
      }
      
      // Set preview image
      const reader = new FileReader();
      reader.onload = (event) => {
        avatarPreview.innerHTML = `<img src="${event.target.result}" alt="Preview">`;
        if (uploadBtnText) uploadBtnText.textContent = 'Change Picture';
      };
      reader.readAsDataURL(file);
    });
  }

  // Generate Default Initials Avatar fallback if typing name
  if (registerName && avatarPreview && fileInput) {
    registerName.addEventListener('blur', () => {
      // Generate initials avatar only if no file has been uploaded yet
      if (fileInput.files.length === 0 && registerName.value.trim().length > 0) {
        const words = registerName.value.trim().split(' ');
        let initials = words[0][0].toUpperCase();
        if (words.length > 1) {
          initials += words[words.length - 1][0].toUpperCase();
        }
        
        avatarPreview.innerHTML = `
          <span style="font-size: 20px; font-weight: 700; color: #FFFFFF; opacity: 0.9;">
            ${initials}
          </span>
        `;
      }
    });
  }

  // ==========================================================================
  // Premium Toast Notification System
  // ==========================================================================
  function showErrorToast(message) {
    document.querySelectorAll('.premium-toast').forEach(el => el.remove());
    
    const toast = document.createElement('div');
    toast.className = 'premium-toast error';
    toast.innerHTML = `
      <div class="toast-content">
        <svg class="toast-icon" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><circle cx="12" cy="12" r="10"></circle><line x1="12" y1="8" x2="12" y2="12"></line><line x1="12" y1="16" x2="12.01" y2="16"></line></svg>
        <span class="toast-message">${message}</span>
      </div>
      <button class="toast-close" aria-label="Close message">&times;</button>
    `;
    
    document.body.appendChild(toast);
    
    setTimeout(() => toast.classList.add('visible'), 50);
    
    toast.querySelector('.toast-close').addEventListener('click', () => {
      toast.classList.remove('visible');
      setTimeout(() => toast.remove(), 300);
    });
    
    setTimeout(() => {
      if (toast.parentNode) {
        toast.classList.remove('visible');
        setTimeout(() => toast.remove(), 300);
      }
    }, 4000);
  }

  // ==========================================================================
  // Form Submission Spinners & Secure Client Validations
  // ==========================================================================
  const loginForm = document.getElementById('loginForm');
  const registerForm = document.getElementById('registerForm');
  const forgotForm = document.getElementById('forgotForm');
  const resetForm = document.getElementById('resetForm');
  
  // Submit handlers
  if (loginForm) {
    loginForm.addEventListener('submit', async (e) => {
      e.preventDefault();
      clearFieldErrors();
      
      if (!validateLoginForm()) {
        showErrorToast("Please correct the highlighted errors.");
        return;
      }
      
      const email = document.getElementById('email').value.trim();
      const password = document.getElementById('password').value;
      const rememberMe = document.getElementById('rememberMe') ? document.getElementById('rememberMe').checked : false;
      const csrfToken = loginForm.querySelector('input[name="csrf_token"]').value;
      
      const submitBtn = loginForm.querySelector('button[type="submit"]');
      const btnText = submitBtn.querySelector('.btn-text');
      const btnSpinner = submitBtn.querySelector('.btn-spinner');
      
      const emailInput = document.getElementById('email');
      const passwordInput = document.getElementById('password');
      const rememberInput = document.getElementById('rememberMe');
      
      // Disable inputs
      emailInput.disabled = true;
      passwordInput.disabled = true;
      if (rememberInput) rememberInput.disabled = true;
      submitBtn.disabled = true;
      
      // Multi-step spinner animation sequences
      btnSpinner.style.display = 'block';
      btnText.style.opacity = '1';
      btnText.textContent = "Authenticating...";
      
      const delay = (ms) => new Promise(resolve => setTimeout(resolve, ms));
      
      try {
        const responsePromise = fetch('/login', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json'
          },
          body: JSON.stringify({
            email: email,
            password: password,
            remember_me: rememberMe,
            csrf_token: csrfToken
          })
        });
        
        await delay(600);
        btnText.textContent = "Verifying Credentials...";
        
        await delay(600);
        btnText.textContent = "Creating Secure Session...";
        
        const response = await responsePromise;
        const data = await response.json();
        
        if (data.success) {
          btnText.textContent = "Success";
          btnSpinner.style.display = 'none';
          
          // Render success checkmark overlay in the card
          const card = loginForm.closest('.auth-card');
          const overlay = document.createElement('div');
          overlay.className = 'success-animation-overlay';
          overlay.innerHTML = `
            <div class="success-checkmark-box">
              <svg class="checkmark-svg" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 52 52">
                <circle class="checkmark-circle" cx="26" cy="26" r="25" fill="none"/>
                <path class="checkmark-check" fill="none" d="M14.1 27.2l7.1 7.2 16.7-16.8"/>
              </svg>
            </div>
            <h3>Welcome Back</h3>
            <p style="color: var(--secondary-text); opacity: 0.85; font-size:14px; margin-top:4px;">${data.name}</p>
          `;
          card.appendChild(overlay);
          
          await delay(1200);
          window.location.href = data.redirect;
        } else {
          // Re-enable inputs
          emailInput.disabled = false;
          passwordInput.disabled = false;
          if (rememberInput) rememberInput.disabled = false;
          submitBtn.disabled = false;
          btnText.textContent = "Sign In to Console";
          btnSpinner.style.display = 'none';
          
          if (data.message === "unverified" && data.link) {
            showErrorToast("Account unverified. Redirecting to verification panel...");
            await delay(1500);
            window.location.href = data.link;
          } else {
            showErrorToast(data.message || "Invalid email or password.");
          }
        }
      } catch (error) {
        console.error("Connection error:", error);
        emailInput.disabled = false;
        passwordInput.disabled = false;
        if (rememberInput) rememberInput.disabled = false;
        submitBtn.disabled = false;
        btnText.textContent = "Sign In to Console";
        btnSpinner.style.display = 'none';
        showErrorToast("Secure connection lost. Please verify your server status.");
      }
    });
  }

  setupSubmitSpinner(registerForm, validateRegisterForm);
  setupSubmitSpinner(forgotForm, validateForgotForm);
  setupSubmitSpinner(resetForm, validateResetForm);

  function setupSubmitSpinner(formElement, validateCallback) {
    if (!formElement) return;
    
    formElement.addEventListener('submit', (e) => {
      clearFieldErrors();
      
      const isValid = validateCallback ? validateCallback() : true;
      
      if (!isValid) {
        e.preventDefault();
        showErrorToast("Please check the form for mistakes.");
        return;
      }
      
      const submitBtn = formElement.querySelector('button[type="submit"]');
      if (submitBtn) {
        const btnText = submitBtn.querySelector('.btn-text');
        const btnSpinner = submitBtn.querySelector('.btn-spinner');
        
        if (btnText && btnSpinner) {
          submitBtn.disabled = true;
          btnText.style.opacity = '0';
          btnSpinner.style.display = 'block';
        }
      }
    });
  }

  function clearFieldErrors() {
    document.querySelectorAll('.form-input').forEach(input => {
      input.classList.remove('input-error');
      input.setAttribute('aria-invalid', 'false');
      input.removeAttribute('aria-describedby');
    });
    document.querySelectorAll('.field-error-msg').forEach(msg => {
      msg.style.display = 'none';
      msg.textContent = '';
      msg.removeAttribute('role');
      msg.removeAttribute('aria-live');
    });
    const globalErr = document.getElementById('globalError');
    if (globalErr) globalErr.style.display = 'none';
  }

  function displayFieldError(inputId, message) {
    const input = document.getElementById(inputId);
    const errorEl = document.getElementById(`${inputId}Error`);
    if (input) {
      input.classList.add('input-error');
      input.setAttribute('aria-invalid', 'true');
      input.setAttribute('aria-describedby', `${inputId}Error`);
    }
    if (errorEl) {
      errorEl.textContent = message;
      errorEl.style.display = 'block';
      errorEl.setAttribute('role', 'alert');
      errorEl.setAttribute('aria-live', 'polite');
    }
  }

  // Form Validation Handlers
  function validateLoginForm() {
    let valid = true;
    const email = document.getElementById('email');
    const password = document.getElementById('password');
    
    if (!email.value.trim()) {
      displayFieldError('email', 'Email address is required.');
      valid = false;
    } else if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email.value.trim())) {
      displayFieldError('email', 'Enter a valid email address.');
      valid = false;
    }
    
    if (!password.value) {
      displayFieldError('password', 'Password is required.');
      valid = false;
    }
    
    return valid;
  }

  function validateRegisterForm() {
    let valid = true;
    const name = document.getElementById('fullname');
    const email = document.getElementById('email');
    const phone = document.getElementById('phone');
    const country = document.getElementById('country');
    const password = document.getElementById('password');
    const confirm = document.getElementById('confirm_password');
    const terms = document.getElementById('terms');
    
    if (!name.value.trim()) {
      displayFieldError('fullname', 'Full Name is required.');
      valid = false;
    }
    
    if (!email.value.trim()) {
      displayFieldError('email', 'Email address is required.');
      valid = false;
    } else if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email.value.trim())) {
      displayFieldError('email', 'Enter a valid email address.');
      valid = false;
    }
    
    if (!phone.value.trim()) {
      displayFieldError('phone', 'Phone Number is required.');
      valid = false;
    }
    
    if (!country.value) {
      displayFieldError('country', 'Please select your country.');
      valid = false;
    }
    
    if (!password.value) {
      displayFieldError('password', 'Password is required.');
      valid = false;
    } else {
      const val = password.value;
      const strongRegex = /^(?=.*[a-z])(?=.*[A-Z])(?=.*[0-9])(?=.*[^A-Za-z0-9]).{8,}$/;
      if (!strongRegex.test(val)) {
        displayFieldError('password', 'Password does not meet the security requirements.');
        valid = false;
      }
    }
    
    if (!confirm.value) {
      displayFieldError('confirm_password', 'Confirm password is required.');
      valid = false;
    } else if (confirm.value !== password.value) {
      displayFieldError('confirm_password', 'Passwords do not match.');
      valid = false;
    }
    
    if (terms && !terms.checked) {
      alert('You must agree to the Terms & Conditions to register.');
      valid = false;
    }
    
    return valid;
  }

  function validateForgotForm() {
    let valid = true;
    const email = document.getElementById('email');
    
    if (!email.value.trim()) {
      displayFieldError('email', 'Email address is required.');
      valid = false;
    } else if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email.value.trim())) {
      displayFieldError('email', 'Enter a valid email address.');
      valid = false;
    }
    
    return valid;
  }

  function validateResetForm() {
    let valid = true;
    const password = document.getElementById('password');
    const confirm = document.getElementById('confirm_password');
    
    if (!password.value) {
      displayFieldError('password', 'Password is required.');
      valid = false;
    } else {
      const val = password.value;
      const strongRegex = /^(?=.*[a-z])(?=.*[A-Z])(?=.*[0-9])(?=.*[^A-Za-z0-9]).{8,}$/;
      if (!strongRegex.test(val)) {
        displayFieldError('password', 'Password does not meet requirements.');
        valid = false;
      }
    }
    
    if (!confirm.value) {
      displayFieldError('confirm_password', 'Confirm password is required.');
      valid = false;
    } else if (confirm.value !== password.value) {
      displayFieldError('confirm_password', 'Passwords do not match.');
      valid = false;
    }
    
    return valid;
  }

  // ==========================================================================
  // Chart.js Configuration for Dashboards / Previews
  // ==========================================================================
  
  // 1. Line Chart: Portfolio Growth
  const ctxPortfolio = document.getElementById('portfolioChart');
  if (ctxPortfolio) {
    const chartGradient = ctxPortfolio.getContext('2d').createLinearGradient(0, 0, 0, 150);
    chartGradient.addColorStop(0, 'rgba(16, 185, 129, 0.25)');
    chartGradient.addColorStop(1, 'rgba(16, 185, 129, 0.0)');

    new Chart(ctxPortfolio, {
      type: 'line',
      data: {
        labels: ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul'],
        datasets: [{
          label: `Portfolio Value (${currencySymbol})`,
          data: [54000, 58200, 61000, 68900, 72000, 78400, 82140],
          borderColor: '#10B981',
          borderWidth: 2,
          pointBackgroundColor: '#10B981',
          pointHoverRadius: 5,
          tension: 0.35,
          fill: true,
          backgroundColor: chartGradient,
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { display: false },
          tooltip: {
            mode: 'index',
            intersect: false,
            backgroundColor: '#081A2F',
            titleFont: { family: 'Inter', size: 10, weight: '600' },
            bodyFont: { family: 'Inter', size: 11 },
            borderColor: 'rgba(255, 255, 255, 0.08)',
            borderWidth: 1,
            displayColors: false,
            padding: 8
          }
        },
        scales: {
          x: {
            grid: { display: false },
            ticks: {
              color: 'rgba(255, 255, 255, 0.4)',
              font: { family: 'Inter', size: 9 }
            }
          },
          y: {
            grid: {
              color: 'rgba(255, 255, 255, 0.04)',
              drawBorder: false
            },
            ticks: {
              color: 'rgba(255, 255, 255, 0.4)',
              font: { family: 'Inter', size: 9 },
              callback: (value) => `${currencySymbol}${value / 1000}k`
            }
          }
        }
      }
    });
  }

  // 2. Doughnut Chart: Expenses Breakdown
  const ctxExpense = document.getElementById('expenseChart');
  if (ctxExpense) {
    new Chart(ctxExpense, {
      type: 'doughnut',
      data: {
        labels: ['SaaS', 'Housing', 'Investing', 'General'],
        datasets: [{
          data: [25, 45, 20, 10],
          backgroundColor: [
            '#10B981',
            '#12395F',
            '#22C55E',
            '#F59E0B'
          ],
          borderColor: 'rgba(8, 26, 47, 0.8)',
          borderWidth: 1.5
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        cutout: '72%',
        plugins: {
          legend: { display: false },
          tooltip: {
            backgroundColor: '#081A2F',
            titleFont: { family: 'Inter', size: 10 },
            bodyFont: { family: 'Inter', size: 11 },
            borderColor: 'rgba(255, 255, 255, 0.08)',
            borderWidth: 1,
            padding: 6,
            callbacks: {
              label: (context) => ` ${context.label}: ${context.raw}%`
            }
          }
        }
      }
    });
  }

  // ==========================================================================
  // Mobile Sidebar Drawer Toggle
  // ==========================================================================
  const hamburgerBtn = document.getElementById('hamburgerBtn');
  const dashSidebar = document.getElementById('dashSidebar');
  const sidebarOverlay = document.getElementById('sidebarOverlay');

  function openSidebar() {
    if (dashSidebar) dashSidebar.classList.add('mobile-open');
    if (sidebarOverlay) sidebarOverlay.classList.add('active');
    if (hamburgerBtn) {
      hamburgerBtn.classList.add('open');
      hamburgerBtn.setAttribute('aria-expanded', 'true');
    }
  }

  function closeSidebar() {
    if (dashSidebar) dashSidebar.classList.remove('mobile-open');
    if (sidebarOverlay) sidebarOverlay.classList.remove('active');
    if (hamburgerBtn) {
      hamburgerBtn.classList.remove('open');
      hamburgerBtn.setAttribute('aria-expanded', 'false');
    }
  }

  if (hamburgerBtn) {
    hamburgerBtn.addEventListener('click', (e) => {
      e.stopPropagation();
      const isOpen = dashSidebar && dashSidebar.classList.contains('mobile-open');
      if (isOpen) {
        closeSidebar();
      } else {
        openSidebar();
      }
    });
  }

  if (sidebarOverlay) {
    sidebarOverlay.addEventListener('click', closeSidebar);
    sidebarOverlay.addEventListener('touchstart', closeSidebar, { passive: true });
  }

  // Header User Dropdown Toggle
  const userDropdownBtn = document.getElementById('headerUserDropdown');
  const userMenu = document.getElementById('headerUserMenu');
  if (userDropdownBtn && userMenu) {
    userDropdownBtn.addEventListener('click', (e) => {
      if (userMenu.contains(e.target)) return;
      e.stopPropagation();
      const isHidden = userMenu.style.display === 'none';
      userMenu.style.display = isHidden ? 'block' : 'none';
      userDropdownBtn.setAttribute('aria-expanded', isHidden ? 'true' : 'false');
    });

    document.addEventListener('click', (e) => {
      if (!userDropdownBtn.contains(e.target)) {
        userMenu.style.display = 'none';
        userDropdownBtn.setAttribute('aria-expanded', 'false');
      }
    });
  }

  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
      closeSidebar();
      if (userMenu) {
        userMenu.style.display = 'none';
        if (userDropdownBtn) userDropdownBtn.setAttribute('aria-expanded', 'false');
      }
    }
  });
});


