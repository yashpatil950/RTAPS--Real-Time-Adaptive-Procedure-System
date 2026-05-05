// Use 2107 for image URLs

// Helper function to get procedures for a specific train
export const getProceduresByTrain = (trainNumber) => {
  const train = trainNumber === 1 ? 'train1' : 'train2';
  return proceduresByTrain[train] || [];
};

// Helper function to get a specific procedure by ID and train
export const getProcedureByTrain = (procedureId, trainNumber) => {
  const train = trainNumber === 1 ? 'train1' : 'train2';
  const procedures = proceduresByTrain[train] || [];
  return procedures.find(p => p.id === parseInt(procedureId));
};

// Helper function to get all procedures (for backward compatibility)
export const getAllProcedures = () => {
  // Return Train 1 procedures by default for backward compatibility
  return proceduresByTrain.train1 || [];
};

// Deep clone function for duplicating procedures
const deepClone = (obj) => JSON.parse(JSON.stringify(obj));

// ============================================================================
// TRAIN 1 PROCEDURES
// ============================================================================
const train1Procedures = [
  {
    id: 1,
    name: "Centrifuge",
    description: "Centrifuge testing procedure for oil samples",
    steps: [
      {
        id: 1,
        stepNumber: 1,
        title: "Take a sample from the oil outlet of the bulk oil treater. The sample tap is located just upstream of LCV – 301A/302A/303A. (Last number correlates to train number).",
        description: "Extract oil sample from bulk oil treater",
        instructions: "Ensure that the centrifuge tubes are cleared and cleaned properly before starting this step.",
        timeThreshold: 43,
        subSteps: [
          {
            id: 59,
            stepNumber: 1,
            title: "Locate the oil outlet sample tap",
            description: "Find the sample tap upstream of LCV",
            instructions: "The sample tap is located just upstream of LCV – 301A/302A/303A",
            imageUrl: "/images/centrifuge/1_1_oil_outlet.png"
          }
        ]
      },
      {
        id: 2,
        stepNumber: 2,
        title: "Samples should be taken in two 200 ml certified centrifuge tubes. Fill tubes to the 100 ml mark.",
        description: "Take samples in certified centrifuge tubes",
        instructions: "Vapors may ignite, causing flashing fire. Wear proper PPE (Gloves and safety glasses). Use Gas Monitor to detect LEL.",
        timeThreshold: 80,
        subSteps: [
          {
            id: 60,
            stepNumber: 1,
            title: "Fill tubes to 100 ml mark",
            description: "Fill certified centrifuge tubes to the specified mark",
            instructions: "Use two 200 ml certified centrifuge tubes and fill each to the 100 ml mark",
            imageUrl: "/images/centrifuge/1_2_100ml.png"
          }
        ]
      },
      {
        id: 6,
        stepNumber: 3,
        title: "Place tubes into heater and let the samples heat to 115-120 degrees.",
        description: "Heat samples to required temperature",
        instructions: "Flammable vapors possibly present. Ensure applied heat does not exceed the vapor temperature of the oil and water.",
        timeThreshold: 559,
        subSteps: [
          {
            id: 65,
            stepNumber: 1,
            title: "Place tubes in heater",
            description: "Insert sample tubes into heating device",
            instructions: "Carefully place tubes in heater and set temperature to 115-120 degrees",
            imageUrl: "/images/centrifuge/1_3.png"
          }
        ]
      },
      {
        id: 11,
        stepNumber: 4,
        title: "Place tubes onto opposite sides of the centrifuge to maintain balance.",
        description: "Place tubes in centrifuge for balance",
        instructions: "",
        timeThreshold: 68,
        subSteps: [
          {
            id: 69,
            stepNumber: 1,
            title: "Load tubes in centrifuge",
            description: "Place heated tubes on opposite sides",
            instructions: "Place tubes onto opposite sides of the centrifuge to maintain proper balance",
            imageUrl: "/images/centrifuge/1_4.png"
          }
        ]
      },
      {
        id: 12,
        stepNumber: 5,
        title: "Spin the centrifuge for five minutes tests at 70 percent power.",
        description: "Run centrifuge at specified power",
        instructions: "Equipment rotating at high rate of speed that could result in serious bodily injury. Ensure centrifuge is fully stopped before opening or operating.",
        timeThreshold: 298,
        subSteps: []
      },
      {
        id: 13,
        stepNumber: 6,
        title: "Obtain readings of combined basic sediment and water in percentages from the tube to the nearest 0.1 ml.",
        description: "Measure basic sediment and water percentages",
        instructions: "Note: Read the bottom of meniscus.",
        timeThreshold: 49,
        subSteps: [
          {
            id: 71,
            stepNumber: 1,
            title: "Read sediment levels",
            description: "Measure basic sediment and water percentages",
            instructions: "Obtain readings to the nearest 0.1 ml. Read the bottom of meniscus.",
            imageUrl: "/images/centrifuge/1_6.png"
          }
        ]
      },
      {
        id: 14,
        stepNumber: 7,
        title: "Average the results from the two different tubes.",
        description: "Average results from both tubes",
        instructions: "",
        timeThreshold: 42,
        subSteps: []
      },
      {
        id: 15,
        stepNumber: 8,
        title: "If your results are questionable, take two more samples.",
        description: "Check if results are questionable",
        instructions: "Note: Samples that are further than .3 ml apart are questionable.",
        timeThreshold: 4,
        subSteps: []
      }
    ]
  },
  {
    id: 2,
    // https://drive.google.com/drive/u/2/folders/1aNRlez3xV2u6JVMYPejhRib-lvGxJKld
    name: "Column Flushing",
    description: "Column flushing procedure for system maintenance",
    steps: [
      {
        id: 20,
        stepNumber: 1,
        title: "Have CRO place ILIC - 101 in Manual Control.",
        description: "Request manual control from CRO",
        instructions: "Grab radios and hand tools as required before starting this step.",
        timeThreshold: 27,
        subSteps: []
      },
      {
        id: 21,
        stepNumber: 2,
        title: "Have CRO communicate when controller is in Manual.",
        description: "Wait for CRO confirmation",
        instructions: "",
        timeThreshold: 14,
        subSteps: []
      },
      {
        id: 22,
        stepNumber: 3,
        title: "Close manual column valve M101 - 9. Lower isolation valve on level column.",
        description: "Close lower isolation valve",
        instructions: "",
        timeThreshold: 10,
        subSteps: [
          {
            id: 54,
            stepNumber: 1,
            title: "Close lower isolation valve",
            description: "Shut the lower manual column valve",
            instructions: "Close manual column valve M101 - 9. Turn valve handle clockwise to close",
            imageUrl: "/images/column_flushing/2_3.png"
          }
        ]
      },
      {
        id: 23,
        stepNumber: 4,
        title: "Close manual column valve M101 - 11. Upper isolation valve on level column.",
        description: "Close upper isolation valve",
        instructions: "",
        timeThreshold: 10,
        subSteps: []
      },
      {
        id: 24,
        stepNumber: 5,
        title: "Remove plug.",
        description: "Remove plug from designated location",
        instructions: "",
        timeThreshold: 51,
        subSteps: []
      },
      {
        id: 25,
        stepNumber: 6,
        title: "Open drain valve on bottom of float cage.",
        description: "Open drain valve",
        instructions: "",
        timeThreshold: 46,
        subSteps: [
          {
            id: 56,
            stepNumber: 1,
            title: "Open drain valve",
            description: "Open valve at bottom of float cage",
            instructions: "Open drain valve on bottom of float cage",
            imageUrl: "/images/column_flushing/2_6.png"
          }
        ]
      },
      {
        id: 26,
        stepNumber: 7,
        title: "Drain fluids into a bucket with secondary containment.",
        description: "Drain accumulated fluids",
        instructions: "Trapped pressure may be present. Uncontrolled pressure release could result in bodily injury or death. Wear gloves and safety glasses.",
        timeThreshold: 75,
        subSteps: [
          {
            id: 57,
            stepNumber: 1,
            title: "Drain fluids",
            description: "Remove accumulated fluids",
            instructions: "Drain fluids into a bucket with secondary containment. Monitor flow rate and container capacity",
            imageUrl: "/images/column_flushing/2_7.png"
          }
        ]
      },
      {
        id: 27,
        stepNumber: 8,
        title: "Remove plug and open vent on top of float cage and vent to a location away from any personnel. Slowly open vent--releasing pressure a little at a time.",
        description: "Vent pressure safely",
        instructions: "Note: This will verify that all fluids have been drained.",
        timeThreshold: 93,
        subSteps: [
          {
            id: 58,
            stepNumber: 1,
            title: "Remove top plug",
            description: "Take out plug from top of float cage",
            instructions: "Remove plug from top of float cage",
            imageUrl: "/images/column_flushing/2_8_1.png"
          },
          {
            id: 59,
            stepNumber: 2,
            title: "Open vent valve",
            description: "Slowly open vent to release pressure",
            instructions: "Open vent on top of float cage and vent to a location away from any personnel. Slowly open vent--releasing pressure a little at a time",
            imageUrl: "/images/column_flushing/2_8_2.png"
          }
        ]
      },
      {
        id: 31,
        stepNumber: 9,
        title: "Close the vent valve and re-install plug.",
        description: "Close vent and reinstall plug",
        instructions: "",
        timeThreshold: 23,
        subSteps: []
      },
      {
        id: 32,
        stepNumber: 10,
        title: "Close the drain valve and re-install plug.",
        description: "Close drain valve and reinstall plug",
        instructions: "",
        timeThreshold: 35,
        subSteps: []
      },
      {
        id: 33,
        stepNumber: 11,
        title: "Open manual column valves M101 - 11. Upper isolation valve on level column.",
        description: "Open upper isolation valve",
        instructions: "",
        timeThreshold: 33,
        subSteps: [
          {
            id: 60,
            stepNumber: 1,
            title: "Open upper isolation valve",
            description: "Restore upper flow path",
            instructions: "Open manual column valves M101 - 11. Upper isolation valve on level column",
            imageUrl: "/images/column_flushing/2_11.png"
          }
        ]
      },
      {
        id: 34,
        stepNumber: 12,
        title: "Open manual column valves M101 - 9. Lower isolation valve on level column.",
        description: "Open lower isolation valve",
        instructions: "",
        timeThreshold: 13,
        subSteps: []
      },
      {
        id: 35,
        stepNumber: 13,
        title: "Observe that the fluid rise and that the ILIC returns to a normal operating condition.",
        description: "Monitor fluid rise and ILIC",
        instructions: "",
        timeThreshold: 69,
        subSteps: []
      },
      {
        id: 36,
        stepNumber: 14,
        title: "Dispose of fluids collected from performing the task by dumping in Wet Oil Tank.",
        description: "Dispose of collected fluids",
        instructions: "",
        timeThreshold: 73,
        subSteps: []
      }
    ]
  },
  {
    id: 3,
    name: "Pressure Testing",
    description: "Pressure testing procedure for system validation",
    steps: [
      {
        id: 41,
        stepNumber: 1,
        title: "Notify Control Room.",
        description: "Inform control room of testing.",
        instructions: "Note: Have communication plan in place. Cover Testing Process and any needed documentation.",
        timeThreshold: 34,
        subSteps: []
      },
      {
        id: 42,
        stepNumber: 2,
        title: "Have CRO place PST-111 in Override/Bypass.",
        description: "Request override/bypass from CRO.",
        instructions: "Note: Have CRO verify when shutdown is in bypass.",
        timeThreshold: 104,
        subSteps: [
          {
            id: 46,
            stepNumber: 1,
            title: "Check tag and verify bypass",
            description: "Verify shutdown is in bypass mode",
            instructions: "Have CRO place PST-111 in Override/Bypass. Verify when shutdown is in bypass",
            imageUrl: "/images/pressure/3_2_checking_tag.png"
          }
        ]
      },
      {
        id: 43,
        stepNumber: 3,
        title: "Close PST-111 isolation valves.",
        description: "Close isolation valves.",
        instructions: "",
        timeThreshold: 111,
        subSteps: [
          {
            id: 49,
            stepNumber: 1,
            title: "Close isolation valves",
            description: "Shut PST-111 isolation valves",
            instructions: "Close PST-111 isolation valves. Turn valve handles clockwise to close",
            imageUrl: "/images/pressure/3_3_close_isolation_valves.png"
          }
        ]
      },
      {
        id: 44,
        stepNumber: 4,
        title: "Make sure test connection is depressured.",
        description: "Verify connection is depressurized.",
        instructions: "",
        timeThreshold: 124,
        subSteps: [
          {
            id: 51,
            stepNumber: 1,
            title: "Depressurize test connection",
            description: "Verify connection is fully depressurized",
            instructions: "Make sure test connection is depressured. Use pressure gauge to confirm zero pressure",
            imageUrl: "/images/pressure/3_4_depressure.png"
          }
        ]
      },
      {
        id: 45,
        stepNumber: 5,
        title: "Connect external pressure testing source.",
        description: "Connect pressure testing source",
        instructions: "",
        timeThreshold: 398,
        subSteps: [
          {
            id: 47,
            stepNumber: 1,
            title: "Connect external pressure source",
            description: "Attach external pressure testing source",
            instructions: "Connect external pressure testing source. Ensure proper connection and test for leaks",
            imageUrl: "/images/pressure/3_5_external_pressure.png"
          }
        ]
      },
      {
        id: 50,
        stepNumber: 6,
        title: "Increase test pressure until PSH is tripped.",
        description: "Increase pressure to trip PSH",
        instructions: "Trapped pressure may be present. Uncontrolled pressure release could result in bodily injury or death. Wear gloves and safety glasses. Note: Have CRO verify when shutdown is active.",
        timeThreshold: 221,
        subSteps: [
          {
            id: 48,
            stepNumber: 1,
            title: "Increase test pressure",
            description: "Raise pressure until PSH trips",
            instructions: "Increase test pressure until PSH is tripped. Monitor pressure levels carefully. Have CRO verify when shutdown is active",
            imageUrl: "/images/pressure/3_6_increase_test_pressure.png"
          }
        ]
      },
      {
        id: 51,
        stepNumber: 7,
        title: "Reduce pressure until PSH is reset.",
        description: "Reduce pressure to reset PSH",
        instructions: "Note: Have CRO verify when shutdown is reset.",
        timeThreshold: 66,
        subSteps: []
      },
      {
        id: 52,
        stepNumber: 8,
        title: "Reduce test pressure until PSL is tripped.",
        description: "Reduce pressure to trip PSL",
        instructions: "Note: Have CRO verify when shutdown is active.",
        timeThreshold: 32,
        subSteps: [
          {
            id: 50,
            stepNumber: 1,
            title: "Reduce pressure for PSL trip",
            description: "Lower pressure until PSL trips",
            instructions: "Reduce test pressure until PSL is tripped. Monitor low pressure switch. Have CRO verify when shutdown is active",
            imageUrl: "/images/pressure/3_8_reduce_test_pressure_psl.png"
          }
        ]
      },
      {
        id: 53,
        stepNumber: 9,
        title: "Reduce test pressure completely.",
        description: "Reduce pressure completely.",
        instructions: "Note: Have CRO verify when shutdown is reset.",
        timeThreshold: 170,
        subSteps: [
          {
            id: 51,
            stepNumber: 1,
            title: "Reduce pressure completely",
            description: "Release all test pressure",
            instructions: "Reduce test pressure completely. Return to atmospheric pressure. Have CRO verify when shutdown is reset",
            imageUrl: "/images/pressure/3_9__test_pressure_completely.png"
          }
        ]
      },
      {
        id: 54,
        stepNumber: 10,
        title: "Disconnect test pressure source. (Close test valve if required)",
        description: "Disconnect test source.",
        instructions: "",
        timeThreshold: 33,
        subSteps: [
          {
            id: 52,
            stepNumber: 1,
            title: "Disconnect test source",
            description: "Remove external pressure source",
            instructions: "Disconnect test pressure source. Close test valve if required",
            imageUrl: "/images/pressure/3_10_disconnect_test_pressure.png"
          }
        ]
      },
      {
        id: 55,
        stepNumber: 11,
        title: "Open PST-111 isolation valve.",
        description: "Open isolation valve.",
        instructions: "",
        timeThreshold: 24,
        subSteps: [
          {
            id: 53,
            stepNumber: 1,
            title: "Reopen isolation valve",
            description: "Restore PST-111 isolation valve",
            instructions: "Open PST-111 isolation valve. Return system to normal operation",
            imageUrl: "/images/pressure/3_11_reopen_isolation_valve.png"
          }
        ]
      },
      {
        id: 56,
        stepNumber: 12,
        title: "Verify Pressure increases to safe operating limits of PST.",
        description: "Verify pressure limits.",
        instructions: "Note: Have CRO verify when shutdown is in reset. Notify CRO testing is complete.",
        timeThreshold: 27,
        subSteps: []
      },
      {
        id: 57,
        stepNumber: 13,
        title: "Remove Override/Bypass",
        description: "Remove override/bypass",
        instructions: "",
        timeThreshold: 21,
        subSteps: []
      },
      {
        id: 58,
        stepNumber: 14,
        title: "Notify the Control Room Operator that equipment is ready to return to service.",
        description: "Notify control room of completion",
        instructions: "",
        timeThreshold: 21,
        subSteps: []
      }
    ]
  }
].map(proc => ({
  ...proc,
  trainNumber: 1,
  name: `${proc.name} - Train 1`
}));

// ============================================================================
// TRAIN 2 PROCEDURES
// ============================================================================
// Define Train 2 procedures separately - customize steps, instructions, thresholds, etc.
// Currently duplicated from Train 1 as a starting point - customize as needed
const train2Procedures = deepClone(train1Procedures).map(proc => {
  const cloned = {
    ...proc,
    trainNumber: 2,
    name: proc.name.replace('Train 1', 'Train 2')
  };
  
  // Customize Train 2 procedures here
  if (proc.id === 2) { // Column Flushing procedure
    // Replace 101 with 102 in steps 1, 3, 4, 11, 12
    cloned.steps = cloned.steps.map(step => {
      if (step.stepNumber === 1 || step.stepNumber === 3 || step.stepNumber === 4 || step.stepNumber === 11 || step.stepNumber === 12) {
        return {
          ...step,
          title: step.title.replace(/101/g, '102')
        };
      }
      return step;
    });
  }
  
  if (proc.id === 3) { // Pressure Testing procedure
    // Replace 111 with 112 in steps 2, 3, 11
    cloned.steps = cloned.steps.map(step => {
      if (step.stepNumber === 2 || step.stepNumber === 3 || step.stepNumber === 11) {
        return {
          ...step,
          title: step.title.replace(/111/g, '112')
        };
      }
      return step;
    });
  }
  
  // Centrifuge (proc.id === 1) - No changes needed
  
  return cloned;
});

// ============================================================================
// EXPORT TRAIN-SPECIFIC PROCEDURES
// ============================================================================
const proceduresByTrain = {
  train1: train1Procedures,
  train2: train2Procedures
};

// Export default procedures (Train 1 for backward compatibility)
export const procedures = proceduresByTrain.train1;
