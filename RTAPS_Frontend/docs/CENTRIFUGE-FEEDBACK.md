# Centrifuge Test Procedure - Feedback Explanations

This document provides adaptive feedback explanations for the Centrifuge Test procedure based on workload probability (p).

## Workload Classification

- **Low (p = 0-0.3)**: No additional feedback
- **Medium (p = 0.3-0.7)**: Simple explanation
- **High (p = 0.7-1)**: Full explanation

---

## Step 1: Take Sample from Oil Outlet

### Medium Workload (Simple Explanation)

- Sample location upstream of LCV ensures representative oil before level control
- Clean tubes prevent contamination that affects BSW accuracy

### High Workload (Full Explanation)

**Why:**
- Sampling upstream of LCV captures true oil composition from bulk oil treater without mixing effects from downstream operations
- Clean tubes are critical - any residual water or sediment will be measured as part of your sample, leading to false high BSW readings

**What:**
- This step extracts a sample that represents the actual oil quality before any level control valve manipulation
- The sample location (upstream of LCV-301A/302A/303A) ensures correct train-specific sampling point

**How:**
- Locate sample tap just upstream of LCV (last number correlates to train: 301A=Train 1, 302A=Train 2, 303A=Train 3)
- Ensure centrifuge tubes are completely clean and dry before use

---

## Step 2: Fill Tubes to 100 ml Mark

### Medium Workload (Simple Explanation)

- Two samples provide redundancy and accuracy verification
- Certified tubes ensure measurement precision
- 100 ml is standard volume for BSW calculation per API standards

### High Workload (Full Explanation)

**Why:**
- Duplicate samples allow averaging and error detection - if results differ by >0.3 ml, it indicates sampling error or contamination
- Certified tubes have calibrated markings ensuring accurate volume measurement; non-certified tubes can have ±2-5% error affecting BSW percentage calculations
- Oil samples contain volatile hydrocarbons that can ignite at room temperature - proper PPE prevents flash fire injuries

**What:**
- Two 200 ml certified centrifuge tubes filled to exactly 100 ml each
- This standardized volume (per API MPMS Chapter 10.4) allows direct percentage reading from tube graduations

**How:**
- Use two 200 ml certified centrifuge tubes and fill each precisely to the 100 ml mark
- Wear proper PPE (gloves and safety glasses) and use Gas Monitor to detect LEL before and during sampling

---

## Step 3: Heat Samples to 115-120°F

### Medium Workload (Simple Explanation)

- Heating breaks oil-water emulsions for accurate separation
- Temperature range ensures proper viscosity reduction without vaporization

### High Workload (Full Explanation)

**Why:**
- Crude oil often contains stable water-in-oil emulsions that won't separate at room temperature - heating destabilizes emulsions by reducing oil viscosity and breaking surface tension
- This temperature range (115-120°F) is specified by ASTM D4007 for reproducible results across different crude types
- Exceeding vapor temperature causes flashing (instant vaporization) which is dangerous and ruins the test

**What:**
- Heating breaks the emulsion, allowing water and sediment to separate from oil during centrifugation
- The sample reaches thermal equilibrium throughout its volume, ensuring complete emulsion breaking

**How:**
- Place tubes into heater and set temperature to 115-120°F (below 115°F: incomplete breaking; above 120°F: risk of vaporization)
- Ensure thermal equilibrium is reached throughout sample volume and monitor to ensure heat does not exceed vapor temperature

---

## Step 4: Place Tubes on Opposite Sides

### Medium Workload (Simple Explanation)

- Balanced loading prevents centrifuge vibration and damage
- Ensures even force distribution during rotation

### High Workload (Full Explanation)

**Why:**
- Centrifuges rotate at high speeds (typically 1500-2000 RPM); unbalanced loads create excessive vibration damaging bearings and motor
- Imbalance poses safety risk from potential rotor failure and can cause inaccurate separation due to uneven forces

**What:**
- Tubes placed on opposite sides create equal moment arms around rotation axis, maintaining dynamic balance
- This prevents centrifuge shutdown, sample loss, or equipment failure requiring costly repairs

**How:**
- Place both heated tubes onto opposite sides of the centrifuge rotor, positioned symmetrically (180° apart)
- Verify tubes are securely seated in rotor slots and rotor is clean before starting

---

## Step 5: Spin at 70% Power for 5 Minutes

### Medium Workload (Simple Explanation)

- 70% power provides sufficient centrifugal force without excessive stress
- 5 minutes allows complete separation of water and sediment by density

### High Workload (Full Explanation)

**Why:**
- Full power creates excessive G-forces that can damage tubes; too low power (<50%) doesn't generate enough force to separate fine particles
- 70% provides optimal balance: ~1000-1500 G-force sufficient for most crude types
- Water droplets and fine sediment particles need time to migrate through oil to bottom (Stokes' law)

**What:**
- Centrifugal force creates artificial gravity field; denser materials (water ~1.0 g/ml, sediment ~2.5 g/ml) migrate outward faster than oil (~0.85 g/ml)
- After 5 minutes at 70% power, water and sediment are fully separated at bottom of tube

**How:**
- Set centrifuge to 70% power and run for exactly 5 minutes (API standard duration)
- Never open centrifuge while spinning - wait for complete stop (typically 30-60 seconds) and verify fully stopped before opening

---

## Step 6: Read BSW to Nearest 0.1 ml

### Medium Workload (Simple Explanation)

- Meniscus reading ensures consistent measurement technique
- 0.1 ml precision required for accurate percentage calculation

### High Workload (Full Explanation)

**Why:**
- Liquid surface curves due to surface tension (meniscus effect) - reading bottom provides consistent reference point across all measurements
- In 100 ml sample, 0.1 ml = 0.1% BSW - industry standard precision required for contractual specifications

**What:**
- You're measuring the combined volume of water (bottom clear layer) and sediment (interface layer) - both indicate oil quality issues
- Accurate reading determines BSW percentage which directly affects oil pricing, equipment operation, and contract compliance

**How:**
- Read the bottom of meniscus (not top) for consistent measurement, positioning eye level to avoid parallax error
- Read immediately after stopping centrifuge to prevent re-emulsification and measure to the nearest 0.1 ml using tube graduations

---

## Step 7: Average Results from Two Tubes

### Medium Workload (Simple Explanation)

- Averaging reduces random measurement errors
- Provides more reliable BSW value than single measurement

### High Workload (Full Explanation)

**Why:**
- Single measurement has higher uncertainty (±0.2-0.3 ml typical); averaging two independent measurements reduces error by √2 factor
- Large difference (>0.3 ml) between tubes indicates sampling inconsistency, measurement error, or equipment problem

**What:**
- Averaging provides more reliable BSW value than single measurement
- The averaged result is used for oil pricing calculations, equipment operation decisions, and contract compliance

**How:**
- Add the two readings together and divide by two: Average BSW = (Reading 1 + Reading 2) / 2
- Compare the two readings - if difference >0.3 ml, results are questionable and should be retested

---

## Step 8: Retake Samples if Results Questionable

### Medium Workload (Simple Explanation)

- >0.3 ml difference indicates measurement error
- Retesting ensures accurate quality control data

### High Workload (Full Explanation)

**Why:**
- 0.3 ml threshold represents 0.3% BSW difference - significant for quality control; API guidelines recommend retesting when difference exceeds this
- Single retest could be outlier; two new samples provide confirmation and identify whether problem is systematic (equipment) or random (technique)

**What:**
- If results differ by >0.3 ml, the test is considered questionable and must be repeated
- Accurate BSW is critical: false high readings cause unnecessary process adjustments, while false low readings lead to quality issues downstream and contract violations

**How:**
- If difference between two tubes >0.3 ml, discard results and take two completely new samples following all previous steps
- Common causes: incomplete emulsion breaking, contaminated tubes, sampling inconsistency, or centrifuge imbalance
