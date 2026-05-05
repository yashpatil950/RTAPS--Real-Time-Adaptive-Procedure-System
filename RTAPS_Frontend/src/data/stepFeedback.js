// Step Feedback Explanations
// Organized by procedure ID and step number
// Workload levels: low (0-0.3), medium (0.3-0.7), high (0.7-1)

export const stepFeedbackData = {
  // Centrifuge (procedure ID: 1)
  1: {
    1: {
      medium: [
        "Sample location upstream of LCV ensures representative oil before level control",
        "Clean tubes prevent contamination that affects BSW accuracy"
      ],
      high: {
        why: [
          "Sampling upstream of LCV captures true oil composition from bulk oil treater without mixing effects from downstream operations",
          "Clean tubes are critical - any residual water or sediment will be measured as part of your sample, leading to false high BSW readings"
        ],
        what: [
          "This step extracts a sample that represents the actual oil quality before any level control valve manipulation",
          "The sample location (upstream of LCV-301A/302A/303A) ensures correct train-specific sampling point"
        ],
        how: [
          "Locate sample tap just upstream of LCV (last number correlates to train: 301A=Train 1, 302A=Train 2, 303A=Train 3)",
          "Ensure centrifuge tubes are completely clean and dry before use"
        ]
      }
    },
    2: {
      medium: [
        "Two samples provide redundancy and accuracy verification",
        "Certified tubes ensure measurement precision",
        "100 ml is standard volume for BSW calculation per API standards"
      ],
      high: {
        why: [
          "Duplicate samples allow averaging and error detection - if results differ by >0.3 ml, it indicates sampling error or contamination",
          "Certified tubes have calibrated markings ensuring accurate volume measurement; non-certified tubes can have ±2-5% error affecting BSW percentage calculations",
          "Oil samples contain volatile hydrocarbons that can ignite at room temperature - proper PPE prevents flash fire injuries"
        ],
        what: [
          "Two 200 ml certified centrifuge tubes filled to exactly 100 ml each",
          "This standardized volume (per API MPMS Chapter 10.4) allows direct percentage reading from tube graduations"
        ],
        how: [
          "Use two 200 ml certified centrifuge tubes and fill each precisely to the 100 ml mark",
          "Wear proper PPE (gloves and safety glasses) and use Gas Monitor to detect LEL before and during sampling"
        ]
      }
    },
    3: {
      medium: [
        "Heating breaks oil-water emulsions for accurate separation",
        "Temperature range ensures proper viscosity reduction without vaporization"
      ],
      high: {
        why: [
          "Crude oil often contains stable water-in-oil emulsions that won't separate at room temperature - heating destabilizes emulsions by reducing oil viscosity and breaking surface tension",
          "This temperature range (115-120°F) is specified by ASTM D4007 for reproducible results across different crude types",
          "Exceeding vapor temperature causes flashing (instant vaporization) which is dangerous and ruins the test"
        ],
        what: [
          "Heating breaks the emulsion, allowing water and sediment to separate from oil during centrifugation",
          "The sample reaches thermal equilibrium throughout its volume, ensuring complete emulsion breaking"
        ],
        how: [
          "Place tubes into heater and set temperature to 115-120°F (below 115°F: incomplete breaking; above 120°F: risk of vaporization)",
          "Ensure thermal equilibrium is reached throughout sample volume and monitor to ensure heat does not exceed vapor temperature"
        ]
      }
    },
    4: {
      medium: [
        "Balanced loading prevents centrifuge vibration and damage",
        "Ensures even force distribution during rotation"
      ],
      high: {
        why: [
          "Centrifuges rotate at high speeds (typically 1500-2000 RPM); unbalanced loads create excessive vibration damaging bearings and motor",
          "Imbalance poses safety risk from potential rotor failure and can cause inaccurate separation due to uneven forces"
        ],
        what: [
          "Tubes placed on opposite sides create equal moment arms around rotation axis, maintaining dynamic balance",
          "This prevents centrifuge shutdown, sample loss, or equipment failure requiring costly repairs"
        ],
        how: [
          "Place both heated tubes onto opposite sides of the centrifuge rotor, positioned symmetrically (180° apart)",
          "Verify tubes are securely seated in rotor slots and rotor is clean before starting"
        ]
      }
    },
    5: {
      medium: [
        "70% power provides sufficient centrifugal force without excessive stress",
        "5 minutes allows complete separation of water and sediment by density"
      ],
      high: {
        why: [
          "Full power creates excessive G-forces that can damage tubes; too low power (<50%) doesn't generate enough force to separate fine particles",
          "70% provides optimal balance: ~1000-1500 G-force sufficient for most crude types",
          "Water droplets and fine sediment particles need time to migrate through oil to bottom (Stokes' law)"
        ],
        what: [
          "Centrifugal force creates artificial gravity field; denser materials (water ~1.0 g/ml, sediment ~2.5 g/ml) migrate outward faster than oil (~0.85 g/ml)",
          "After 5 minutes at 70% power, water and sediment are fully separated at bottom of tube"
        ],
        how: [
          "Set centrifuge to 70% power and run for exactly 5 minutes (API standard duration)",
          "Never open centrifuge while spinning - wait for complete stop (typically 30-60 seconds) and verify fully stopped before opening"
        ]
      }
    },
    6: {
      medium: [
        "Meniscus reading ensures consistent measurement technique",
        "0.1 ml precision required for accurate percentage calculation"
      ],
      high: {
        why: [
          "Liquid surface curves due to surface tension (meniscus effect) - reading bottom provides consistent reference point across all measurements",
          "In 100 ml sample, 0.1 ml = 0.1% BSW - industry standard precision required for contractual specifications"
        ],
        what: [
          "You're measuring the combined volume of water (bottom clear layer) and sediment (interface layer) - both indicate oil quality issues",
          "Accurate reading determines BSW percentage which directly affects oil pricing, equipment operation, and contract compliance"
        ],
        how: [
          "Read the bottom of meniscus (not top) for consistent measurement, positioning eye level to avoid parallax error",
          "Read immediately after stopping centrifuge to prevent re-emulsification and measure to the nearest 0.1 ml using tube graduations"
        ]
      }
    },
    7: {
      medium: [
        "Averaging reduces random measurement errors",
        "Provides more reliable BSW value than single measurement"
      ],
      high: {
        why: [
          "Single measurement has higher uncertainty (±0.2-0.3 ml typical); averaging two independent measurements reduces error by √2 factor",
          "Large difference (>0.3 ml) between tubes indicates sampling inconsistency, measurement error, or equipment problem"
        ],
        what: [
          "Averaging provides more reliable BSW value than single measurement",
          "The averaged result is used for oil pricing calculations, equipment operation decisions, and contract compliance"
        ],
        how: [
          "Add the two readings together and divide by two: Average BSW = (Reading 1 + Reading 2) / 2",
          "Compare the two readings - if difference >0.3 ml, results are questionable and should be retested"
        ]
      }
    },
    8: {
      medium: [
        ">0.3 ml difference indicates measurement error",
        "Retesting ensures accurate quality control data"
      ],
      high: {
        why: [
          "0.3 ml threshold represents 0.3% BSW difference - significant for quality control; API guidelines recommend retesting when difference exceeds this",
          "Single retest could be outlier; two new samples provide confirmation and identify whether problem is systematic (equipment) or random (technique)"
        ],
        what: [
          "If results differ by >0.3 ml, the test is considered questionable and must be repeated",
          "Accurate BSW is critical: false high readings cause unnecessary process adjustments, while false low readings lead to quality issues downstream and contract violations"
        ],
        how: [
          "If difference between two tubes >0.3 ml, discard results and take two completely new samples following all previous steps",
          "Common causes: incomplete emulsion breaking, contaminated tubes, sampling inconsistency, or centrifuge imbalance"
        ]
      }
    }
  },
  // Column Flushing (procedure ID: 2)
  2: {
    1: {
      medium: [
        "Manual control prevents automatic level adjustments during flushing",
        "Ensures safe isolation of column from process control"
      ],
      high: {
        why: [
          "Automatic control would fight against your draining operation - controller would try to maintain level by opening valves, creating safety hazard",
          "Manual mode locks controller output, preventing interference with maintenance work"
        ],
        what: [
          "Controller is placed in manual mode, locking its output and preventing automatic valve movements",
          "This isolates the column from automatic process control, allowing safe manual intervention"
        ],
        how: [
          "Request CRO to place ILIC-101 (or ILIC-102 for Train 2) in Manual Control",
          "Grab radios and hand tools as required before starting this step"
        ]
      }
    },
    2: {
      medium: [
        "Verification ensures controller is actually in manual mode",
        "Prevents proceeding with unsafe conditions"
      ],
      high: {
        why: [
          "Visual indicators can be misleading or delayed; CRO has real-time DCS view of actual controller state",
          "Prevents false assumption that could lead to dangerous situation"
        ],
        what: [
          "CRO verifies that controller output is locked, no automatic valve movements are occurring, and system is ready for manual intervention"
        ],
        how: [
          "Wait for explicit verbal or radio confirmation from CRO",
          "Do not proceed based on visual indicators alone"
        ]
      }
    },
    3: {
      medium: [
        "Isolates column bottom to prevent process fluid from entering during flushing",
        "Creates controlled drainage path"
      ],
      high: {
        why: [
          "Prevents process fluids from flowing into column during maintenance and protects personnel from exposure to hot, pressurized, or hazardous fluids",
          "Bottom connection is where fluid accumulates - closing it first prevents new fluid from entering while you drain"
        ],
        what: [
          "Lower isolation valve is closed, creating barrier between column and process at bottom connection",
          "This allows safe depressurization and drainage without process interference"
        ],
        how: [
          "Close manual column valve M101-9 (lower isolation valve on level column), turning handle clockwise to close",
          "Verify valve is fully closed (check handle position, listen for no flow sound)"
        ]
      }
    },
    4: {
      medium: [
        "Completes column isolation from process",
        "Prevents fluid entry from top connections"
      ],
      high: {
        why: [
          "Completes full isolation of column from process and prevents vapor or liquid from entering from overhead connections",
          "If closed first, pressure could build in column - closing lower first allows any trapped pressure to vent upward"
        ],
        what: [
          "Upper isolation valve is closed, completing full isolation of column from process",
          "With both valves closed, column is now isolated from process - safe for maintenance work"
        ],
        how: [
          "Close manual column valve M101-11 (upper isolation valve on level column), turning handle clockwise to close",
          "Verify both upper and lower valves are fully closed before proceeding"
        ]
      }
    },
    5: {
      medium: [
        "Provides access point for drainage",
        "Standard maintenance procedure"
      ],
      high: {
        why: [
          "Creates opening for fluid drainage from float cage and allows connection of drain hose or bucket for controlled drainage"
        ],
        what: [
          "Plug is removed from drain connection at bottom of float cage, creating the opening needed for fluid drainage"
        ],
        how: [
          "Locate plug on drain connection at bottom of float cage",
          "Crack plug slowly first to verify no trapped pressure, then use proper tools to remove completely"
        ]
      }
    },
    6: {
      medium: [
        "Allows accumulated fluids to drain from float cage",
        "Removes water, sediment, and contaminants"
      ],
      high: {
        why: [
          "Float cage accumulates water, sediment, and process contaminants that interfere with float operation, cause corrosion, or jam float causing false level readings",
          "Regular flushing prevents equipment failure and maintains accurate level measurement"
        ],
        what: [
          "Drain valve is opened, allowing accumulated fluids to flow out of float cage",
          "This removes water, sediment, and contaminants that interfere with level measurement accuracy"
        ],
        how: [
          "Open drain valve on bottom of float cage and monitor flow to ensure proper drainage",
          "Be prepared for potential trapped pressure release"
        ]
      }
    },
    7: {
      medium: [
        "Secondary containment prevents environmental spills",
        "Proper disposal required for process fluids"
      ],
      high: {
        why: [
          "Process fluids are often hazardous (hydrocarbons, chemicals) - spills can cause environmental violations and safety hazards; regulatory requirement for secondary containment",
          "Column may contain pressurized fluids even after isolation - sudden release can cause violent fluid ejection"
        ],
        what: [
          "Fluids (water, hydrocarbons, sediment) are drained into bucket with secondary containment",
          "This collects all drained material for proper disposal per environmental regulations"
        ],
        how: [
          "Position bucket with secondary containment under drain valve and wear gloves and safety glasses (PPE)",
          "Monitor flow rate (sudden increase indicates pressure release) and bucket capacity to prevent overflow"
        ]
      }
    },
    8: {
      medium: [
        "Venting verifies complete drainage",
        "Slow venting prevents sudden pressure release"
      ],
      high: {
        why: [
          "Verifies all fluids have drained (if air/vapor comes out, column is empty) and releases any trapped pressure or vapor",
          "Sudden pressure release can cause violent fluid ejection, equipment damage, or safety hazard to personnel"
        ],
        what: [
          "Top plug is removed and vent is opened, allowing pressure to escape",
          "If only vapor/air comes out = drainage complete; if liquid comes out = drainage incomplete, continue draining"
        ],
        how: [
          "Remove plug from top of float cage and open vent slowly, releasing pressure a little at a time",
          "Vent to location away from personnel and monitor what comes out: vapor/air indicates complete drainage"
        ]
      }
    },
    9: {
      medium: [
        "Seals column after verification",
        "Prepares for refilling operation"
      ],
      high: {
        why: [
          "Seals column to prevent contamination during refill and maintains controlled environment for level restoration",
          "Prevents air ingress that could affect level measurement"
        ],
        what: [
          "Vent valve is closed and plug is reinstalled, sealing the top of float cage",
          "Column is now sealed and ready for refilling operation"
        ],
        how: [
          "Close the vent valve completely, clean plug threads, and reinstall plug - tighten to specification (not too tight)",
          "Verify no leaks after installation"
        ]
      }
    },
    10: {
      medium: [
        "Seals bottom connection",
        "Completes column sealing for refill"
      ],
      high: {
        why: [
          "Prevents fluid loss during refill and ensures proper level restoration",
          "Bottom plug is last to be installed (after drain closed) - ensures any remaining fluid doesn't leak out"
        ],
        what: [
          "Drain valve is closed and bottom plug is reinstalled",
          "Column is now completely sealed and ready for refilling"
        ],
        how: [
          "Close the drain valve completely, clean plug threads, and reinstall bottom plug ensuring complete seal",
          "Check for leaks around plug and valve before proceeding"
        ]
      }
    },
    11: {
      medium: [
        "Restores process connection from top",
        "Allows column to refill with process fluid"
      ],
      high: {
        why: [
          "Allows process fluid to enter from top (normal flow direction) and prevents air entrapment by filling from top down",
          "Opening lower valve first could cause rapid fill or pressure issues"
        ],
        what: [
          "Upper isolation valve is opened, restoring process connection from top",
          "Process fluid flows in from overhead connections, allowing column to fill gradually"
        ],
        how: [
          "Open manual column valve M101-11 (upper isolation valve on level column) slowly to allow gradual pressure equalization",
          "Monitor for proper fluid flow and level rise"
        ]
      }
    },
    12: {
      medium: [
        "Completes restoration of process connections",
        "Returns column to normal operation"
      ],
      high: {
        why: [
          "Restores normal process flow path and allows column to function in normal operation mode",
          "Column should be partially filled before opening bottom - prevents sudden flow surges"
        ],
        what: [
          "Lower isolation valve is opened, completing restoration of process connections",
          "Column now connected to process at both ends with normal flow path restored"
        ],
        how: [
          "Open manual column valve M101-9 (lower isolation valve on level column) after upper valve and after column has partially filled",
          "Open slowly to allow gradual return to normal operation"
        ]
      }
    },
    13: {
      medium: [
        "Verifies column is refilling properly",
        "Confirms level controller returning to automatic operation"
      ],
      high: {
        why: [
          "Confirms flushing was successful (no blockages) and verifies equipment integrity after maintenance",
          "Ensures level measurement is working correctly and validates that system is ready for automatic control"
        ],
        what: [
          "Fluid level rises in column (visual or gauge indication) and ILIC controller responds to level changes",
          "Normal operating condition: Level stabilizes at setpoint, controller maintains level automatically, no alarms"
        ],
        how: [
          "Observe fluid level rising in column and monitor ILIC controller response to level changes",
          "Check for no leaks from connections or valves and verify smooth transition back to normal operation"
        ]
      }
    },
    14: {
      medium: [
        "Proper disposal prevents environmental issues",
        "Wet Oil Tank is designated collection point"
      ],
      high: {
        why: [
          "Designated collection point for process fluids meets environmental disposal requirements and allows recovery of hydrocarbons for reprocessing",
          "Improper disposal can result in environmental violations, safety hazards, and lost product recovery"
        ],
        what: [
          "Collected fluids (water, hydrocarbons, sediment) are transferred to Wet Oil Tank",
          "May contain recoverable oil that can be reprocessed"
        ],
        how: [
          "Transfer fluids from secondary containment to Wet Oil Tank",
          "Document disposal (may be required for environmental compliance) and clean secondary containment for next use"
        ]
      }
    }
  },
  // Pressure Testing (procedure ID: 3)
  3: {
    1: {
      medium: [
        "Ensures CRO is aware of testing activities",
        "Establishes communication protocol for coordination"
      ],
      high: {
        why: [
          "CRO monitors entire process - needs to know about testing that affects operations and can prepare for bypass operations",
          "Establishes communication channel for coordination during test and documents testing activity for operational records"
        ],
        what: [
          "Communication plan is established covering testing process, timeline, check-in points, documentation requirements, and CRO support needed"
        ],
        how: [
          "Notify Control Room before starting testing with communication plan in place",
          "Cover Testing Process and any needed documentation, establishing check-in points and expectations for CRO support"
        ]
      }
    },
    2: {
      medium: [
        "Bypass prevents safety shutdown during testing",
        "Allows controlled pressure application without triggering trips"
      ],
      high: {
        why: [
          "Testing will intentionally exceed normal operating pressure to test switch - without bypass, system would shutdown during test, preventing completion",
          "Safety systems require authorized access (typically CRO level) - prevents unauthorized bypass that could create unsafe conditions"
        ],
        what: [
          "PST is placed in Override/Bypass mode, temporarily disabling automatic safety shutdown",
          "System can now be tested without triggering shutdowns"
        ],
        how: [
          "Request CRO to place PST-111 (or PST-112 for Train 2) in Override/Bypass",
          "Have CRO verify when shutdown is in bypass and verify bypass is actually active through visual/DCS confirmation before proceeding"
        ]
      }
    },
    3: {
      medium: [
        "Isolates pressure switch from process pressure",
        "Allows external test pressure application without process interference"
      ],
      high: {
        why: [
          "Process pressure would interfere with test pressure readings; isolation allows controlled test pressure application",
          "Safety: Isolates test area from live process; typically two isolation valves for double block and bleed safety"
        ],
        what: [
          "Isolation valves are closed, creating barrier between process and test connection",
          "Allows test pressure to be applied independently without process interference"
        ],
        how: [
          "Close PST-111 isolation valves (or PST-112 for Train 2), turning valve handles clockwise to close",
          "Verify fully closed (check handle position, no pressure indication) and ensure both valves are closed"
        ]
      }
    },
    4: {
      medium: [
        "Ensures test connection is at atmospheric pressure",
        "Prevents pressure lock that could affect test accuracy"
      ],
      high: {
        why: [
          "Residual pressure in test connection would add to test pressure, causing false readings and leading to incorrect switch calibration",
          "Safety: Prevents sudden pressure release when connecting test source"
        ],
        what: [
          "Test connection is depressurized to atmospheric pressure (zero pressure)",
          "This ensures accurate test pressure readings and safe equipment connection"
        ],
        how: [
          "Use pressure gauge on test connection to verify zero pressure (atmospheric)",
          "Visual check: No hissing or pressure indication; verify completely before proceeding"
        ]
      }
    },
    5: {
      medium: [
        "Provides controlled pressure source for testing",
        "Allows precise pressure application and measurement"
      ],
      high: {
        why: [
          "Process pressure is variable and uncontrolled - external source provides precise control needed for switch testing",
          "Allows testing at specific pressure setpoints with controlled, measurable pressure independent of process"
        ],
        what: [
          "External pressure source is connected to test connection",
          "Provides controlled pressure for accurate switch testing with gradual pressure increase/decrease capability"
        ],
        how: [
          "Connect external pressure source (hydraulic pump, nitrogen cylinder, or compressed air) with proper fittings to prevent leaks",
          "Install pressure gauge to monitor applied pressure and include relief valve for safety",
          "After connection, verify no leaks before proceeding - leaks affect test accuracy and create safety hazard"
        ]
      }
    },
    6: {
      medium: [
        "PSH (Pressure Safety High) should trip at setpoint",
        "Verifies high-pressure protection is functioning"
      ],
      high: {
        why: [
          "PSH protects equipment from over-pressurization and initiates shutdown if pressure exceeds safe operating limit - critical safety function",
          "Regulatory requirement (BSEE: monthly testing) ensures safety system will function in emergency and verifies switch calibration"
        ],
        what: [
          "Pressure is gradually increased until PSH switch trips at its setpoint",
          "Exact trip pressure is noted and compared to setpoint (should match within tolerance, typically ±2-5%)"
        ],
        how: [
          "Gradually increase pressure (prevents overshoot) while monitoring pressure gauge continuously",
          "Note exact pressure when switch trips and compare to setpoint",
          "Wear PPE (gloves, safety glasses) and have CRO verify when shutdown is active"
        ]
      }
    },
    7: {
      medium: [
        "PSH must reset before testing PSL",
        "Verifies switch returns to normal state"
      ],
      high: {
        why: [
          "PSH is latching switch - stays tripped until pressure drops below reset point; must reset before testing low-pressure switch (PSL)",
          "If switch doesn't reset, it indicates switch malfunction, mechanical binding, or calibration issue"
        ],
        what: [
          "Pressure is reduced until PSH switch resets",
          "Reset point is typically 5-10% below trip point (hysteresis) - prevents switch from chattering near setpoint"
        ],
        how: [
          "Gradually reduce pressure from trip point while monitoring pressure gauge",
          "Note exact pressure when switch resets and have CRO verify shutdown is reset"
        ]
      }
    },
    8: {
      medium: [
        "PSL (Pressure Safety Low) protects against under-pressurization",
        "Verifies low-pressure protection is functioning"
      ],
      high: {
        why: [
          "PSL protects against under-pressurization conditions and prevents equipment damage from low pressure (vacuum, leaks)",
          "Regulatory compliance requirement - safety system must respond to low-pressure conditions"
        ],
        what: [
          "Pressure is reduced until PSL switch trips at its setpoint",
          "Switch initiates shutdown when low-pressure trip point is reached"
        ],
        how: [
          "Continue reducing pressure from PSH reset point while monitoring pressure gauge continuously",
          "Note exact pressure when PSL trips, compare to setpoint, and have CRO verify when shutdown is active"
        ]
      }
    },
    9: {
      medium: [
        "Returns system to atmospheric pressure",
        "Prepares for test equipment disconnection"
      ],
      high: {
        why: [
          "Safety: No residual pressure when disconnecting test equipment prevents sudden pressure release during disconnection",
          "Disconnecting under pressure can cause violent pressure release, equipment damage, or personnel injury"
        ],
        what: [
          "All test pressure is released, returning system to atmospheric pressure",
          "System is now in safe state for equipment disconnection"
        ],
        how: [
          "Gradually reduce pressure to zero (atmospheric) and verify pressure gauge reads zero",
          "Confirm safe to disconnect equipment and have CRO verify when shutdown is reset"
        ]
      }
    },
    10: {
      medium: [
        "Removes test equipment",
        "Prepares system for return to normal operation"
      ],
      high: {
        why: [
          "Test equipment is no longer needed and must be removed before restoring process connections",
          "If present, closing test valve before disconnecting prevents any residual pressure release"
        ],
        what: [
          "External pressure source is disconnected from test connection",
          "System is prepared for restoration of process connections"
        ],
        how: [
          "Verify zero pressure before disconnecting and close test valve first (if present) to isolate",
          "Disconnect slowly to check for residual pressure and use proper tools and techniques"
        ]
      }
    },
    11: {
      medium: [
        "Restores process connection to pressure switch",
        "Returns switch to normal monitoring function"
      ],
      high: {
        why: [
          "Restores process pressure connection to switch and returns switch to normal monitoring mode",
          "Test equipment must be removed first - prevents mixing test pressure with process pressure"
        ],
        what: [
          "Isolation valve is opened, restoring process connection to pressure switch",
          "Switch returns to normal monitoring function"
        ],
        how: [
          "Open PST-111 isolation valve (or PST-112 for Train 2) slowly to allow gradual pressure equalization",
          "Monitor for proper pressure restoration"
        ]
      }
    },
    12: {
      medium: [
        "Confirms system is returning to normal operation",
        "Validates pressure switch is monitoring correctly"
      ],
      high: {
        why: [
          "Confirms system integrity after testing and validates that isolation didn't cause issues",
          "Pressure should be above PSL setpoint and below PSH setpoint - within normal operating range"
        ],
        what: [
          "Process pressure is restoring and within normal operating range",
          "Switch is responding to process pressure correctly with no leaks or abnormal conditions"
        ],
        how: [
          "Verify process pressure is restoring and check pressure is within normal operating range (above PSL, below PSH)",
          "Monitor switch response to process pressure and notify CRO testing is complete"
        ]
      }
    },
    13: {
      medium: [
        "Restores automatic safety protection",
        "Returns system to normal safety mode"
      ],
      high: {
        why: [
          "Testing is complete - no longer need to prevent shutdowns; must restore automatic safety protection",
          "System is unprotected if bypass remains active - safety hazard"
        ],
        what: [
          "Bypass is removed, restoring automatic safety protection",
          "System returns to normal safety mode with full interlocks active"
        ],
        how: [
          "Request CRO to remove Override/Bypass",
          "CRO ensures proper restoration of safety systems and verifies safety systems are active"
        ]
      }
    },
    14: {
      medium: [
        "Final communication confirms testing complete",
        "Documents system status for operations"
      ],
      high: {
        why: [
          "Confirms all testing steps completed and documents system is ready for normal operation",
          "Completes communication protocol established in Step 1; notification may be logged for compliance and operational records"
        ],
        what: [
          "CRO is informed that testing completed successfully, all safety systems restored, equipment ready for normal operation, and any issues or concerns noted"
        ],
        how: [
          "Notify the Control Room Operator that equipment is ready to return to service",
          "Provide summary of testing results and report any issues or concerns"
        ]
      }
    }
  }
};

// Helper function to get feedback for a step
export const getStepFeedback = (procedureId, stepNumber, workloadLevel) => {
  const procedureFeedback = stepFeedbackData[procedureId];
  if (!procedureFeedback) return null;
  
  const stepFeedback = procedureFeedback[stepNumber];
  if (!stepFeedback) return null;
  
  if (workloadLevel === 'medium' && stepFeedback.medium) {
    return { type: 'medium', content: stepFeedback.medium };
  } else if (workloadLevel === 'high' && stepFeedback.high) {
    return { type: 'high', content: stepFeedback.high };
  }
  
  return null;
};

// Helper function to determine workload level from probability
export const getWorkloadLevel = (probability) => {
  if (probability >= 0.7) return 'high';
  if (probability >= 0.3) return 'medium';
  return 'low';
};
