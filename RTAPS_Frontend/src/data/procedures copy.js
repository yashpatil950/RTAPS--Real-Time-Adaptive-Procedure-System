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
        title: "Prepare to start task",
        description: "Get ready to begin centrifuge testing",
        instructions: "Gather necessary equipment and safety gear",
        timeThreshold: 43,
        subSteps: [
          {
            id: 59,
            stepNumber: 1,
            title: "Review procedure",
            description: "Read through the centrifuge testing procedure",
            instructions: "Familiarize yourself with all steps before starting"
          },
          {
            id: 60,
            stepNumber: 2,
            title: "Gather equipment",
            description: "Collect all necessary testing equipment",
            instructions: "Get centrifuge tubes, heater, and safety gear",
            imageUrl: "/images/centrifuge/prepare.png"
          },
          {
            id: 61,
            stepNumber: 3,
            title: "Check workspace",
            description: "Ensure workspace is clean and organized",
            instructions: "Clear area and verify proper lighting"
          }
        ]
      },
      {
        id: 5,
        stepNumber: 2,
        title: "Take sample from oil outlet",
        description: "Extract oil sample from bulk oil treater",
        instructions: "Use certified centrifuge tubes to collect 200ml samples",
        timeThreshold: 80,
        subSteps: [
          {
            id: 62,
            stepNumber: 1,
            title: "Prepare sampling container",
            description: "Get certified centrifuge tubes ready",
            instructions: "Ensure tubes are clean and properly labeled"
          },
          {
            id: 63,
            stepNumber: 2,
            title: "Extract oil sample",
            description: "Collect 200ml sample from bulk oil treater",
            instructions: "Use proper sampling technique to get representative sample",
            imageUrl: "/images/centrifuge/take_sample.png"
          },
          {
            id: 64,
            stepNumber: 3,
            title: "Label and secure sample",
            description: "Properly label and secure the collected sample",
            instructions: "Ensure sample is properly identified and stored"
          }
        ]
      },
      {
        id: 6,
        stepNumber: 3,
        title: "Heat samples",
        description: "Heat samples to required temperature",
        instructions: "Place tubes in heater at 115-120 degrees",
        timeThreshold: 559,
        subSteps: [
          {
            id: 65,
            stepNumber: 1,
            title: "Prepare heater",
            description: "Set up heating device for samples",
            instructions: "Ensure heater is clean and ready for use"
          },
          {
            id: 66,
            stepNumber: 2,
            title: "Place tubes in heater",
            description: "Insert sample tubes into heating device",
            instructions: "Carefully place tubes in heater at proper position",
            imageUrl: "/images/centrifuge/heater.png"
          },
          {
            id: 67,
            stepNumber: 3,
            title: "Set temperature",
            description: "Adjust heater to 115-120 degrees",
            instructions: "Set and verify temperature setting"
          },
          {
            id: 68,
            stepNumber: 4,
            title: "Monitor heating process",
            description: "Watch temperature and heating time",
            instructions: "Ensure samples reach target temperature safely"
          }
        ]
      },
      {
        id: 11,
        stepNumber: 4,
        title: "Load centrifuge",
        description: "Place tubes in centrifuge for balance",
        instructions: "Ensure proper balance by placing tubes on opposite sides",
        timeThreshold: 68,
        subSteps: [
          {
            id: 69,
            stepNumber: 1,
            title: "Check centrifuge balance",
            description: "Verify centrifuge is properly balanced",
            instructions: "Ensure tubes are placed on opposite sides for balance"
          },
          {
            id: 70,
            stepNumber: 2,
            title: "Load sample tubes",
            description: "Place heated tubes in centrifuge",
            instructions: "Carefully place tubes in designated positions",
            imageUrl: "/images/centrifuge/centrifuge_4.png"
          },
          {
            id: 71,
            stepNumber: 3,
            title: "Verify loading",
            description: "Double-check tube placement and balance",
            instructions: "Ensure all tubes are properly secured and balanced"
          }
        ]
      },
      {
        id: 12,
        stepNumber: 5,
        title: "Spin centrifuge",
        description: "Run centrifuge at specified power",
        instructions: "Spin for five minutes at 70% power",
        timeThreshold: 298,
        subSteps: []
      },
      {
        id: 13,
        stepNumber: 6,
        title: "Read sediment levels",
        description: "Measure basic sediment and water percentages",
        instructions: "Record readings to nearest 0.1ml",
        timeThreshold: 49,
        subSteps: []
      },
      {
        id: 14,
        stepNumber: 7,
        title: "Calculate average",
        description: "Average results from both tubes",
        instructions: "Compute mean of the two measurements",
        timeThreshold: 42,
        subSteps: []
      },
      {
        id: 15,
        stepNumber: 8,
        title: "Verify results",
        description: "Check if results are questionable",
        instructions: "Take additional samples if needed",
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
        id: 16,
        stepNumber: 1,
        title: "Prepare to start task",
        description: "Get ready to begin column flushing",
        instructions: "Review procedure and gather equipment",
        timeThreshold: 200,
        subSteps: [
          {
            id: 17,
            stepNumber: 1,
            title: "Read procedure",
            description: "Review column flushing procedure",
            instructions: "Carefully read all steps"
          },
          {
            id: 18,
            stepNumber: 2,
            title: "Gather safety equipment",
            description: "Collect necessary safety gear",
            instructions: "Get gloves, goggles, and tools"
          },
          {
            id: 19,
            stepNumber: 3,
            title: "Check workspace",
            description: "Ensure area is clear and safe",
            instructions: "Verify proper lighting and access"
          }
        ]
      },
      {
        id: 20,
        stepNumber: 2,
        title: "Request manual control",
        description: "Ask CRO to put system in manual control",
        instructions: "Communicate with control room operator",
        timeThreshold: 27,
        subSteps: []
      },
      {
        id: 21,
        stepNumber: 3,
        title: "Confirm manual control",
        description: "Verify controller is in manual mode",
        instructions: "Wait for CRO confirmation",
        timeThreshold: 14,
        subSteps: []
      },
      {
        id: 22,
        stepNumber: 4,
        title: "Close isolation valves",
        description: "Close upper and lower isolation valves",
        instructions: "Shut both manual column valves",
        timeThreshold: 10,
        subSteps: [
          {
            id: 54,
            stepNumber: 1,
            title: "Close lower isolation valve",
            description: "Shut the lower manual column valve",
            instructions: "Turn valve handle clockwise to close",
            imageUrl: "/images/column_flushing/close_lowervalve.png"
          },
          {
            id: 55,
            stepNumber: 2,
            title: "Close upper isolation valve",
            description: "Shut the upper manual column valve",
            instructions: "Turn valve handle clockwise to close",
            imageUrl: "/images/column_flushing/close_uppervalve.png"
          }
        ]
      },
      {
        id: 23,
        stepNumber: 5,
        title: "Remove plugs",
        description: "Take out necessary plugs",
        instructions: "Remove plugs from designated locations",
        timeThreshold: 51,
        subSteps: []
      },
      {
        id: 24,
        stepNumber: 6,
        title: "Open drain valve",
        description: "Open valve at bottom of cage",
        instructions: "Release fluids through drain",
        timeThreshold: 46,
        subSteps: []
      },
      {
        id: 25,
        stepNumber: 7,
        title: "Drain fluids",
        description: "Remove accumulated fluids",
        instructions: "Collect fluids in appropriate container",
        timeThreshold: 75,
        subSteps: [
          {
            id: 56,
            stepNumber: 1,
            title: "Position drain container",
            description: "Place container under drain valve",
            instructions: "Ensure container can handle fluid volume"
          },
          {
            id: 57,
            stepNumber: 2,
            title: "Open drain valve",
            description: "Open valve to release accumulated fluids",
            instructions: "Monitor flow rate and container capacity",
            imageUrl: "/images/column_flushing/drain.png"
          },
          {
            id: 58,
            stepNumber: 3,
            title: "Monitor drainage",
            description: "Watch for complete fluid removal",
            instructions: "Ensure all fluids are drained before proceeding"
          }
        ]
      },
      {
        id: 26,
        stepNumber: 8,
        title: "Vent pressure",
        description: "Slowly release system pressure",
        instructions: "Open vent at top and remove plug",
        timeThreshold: 93,
        subSteps: [
          {
            id: 27,
            stepNumber: 1,
            title: "Remove top plug",
            description: "Take out plug from top of cage",
            instructions: "Use appropriate tools carefully"
          },
          {
            id: 28,
            stepNumber: 2,
            title: "Open vent valve",
            description: "Slowly open vent to release pressure",
            instructions: "Monitor pressure gauge"
          },
          {
            id: 29,
            stepNumber: 3,
            title: "Wait for depressurization",
            description: "Allow pressure to drop safely",
            instructions: "Watch for pressure indicators"
          },
          {
            id: 30,
            stepNumber: 4,
            title: "Close vent valve",
            description: "Shut vent when pressure is released",
            instructions: "Secure valve properly"
          }
        ]
      },
      {
        id: 31,
        stepNumber: 9,
        title: "Reinstall plugs",
        description: "Replace plugs and close vent",
        instructions: "Secure all openings properly",
        timeThreshold: 23,
        subSteps: []
      },
      {
        id: 32,
        stepNumber: 10,
        title: "Close drain valve",
        description: "Shut drain and replace plug",
        instructions: "Ensure all valves are properly closed",
        timeThreshold: 35,
        subSteps: []
      },
      {
        id: 33,
        stepNumber: 11,
        title: "Open upper isolation",
        description: "Open upper isolation valve",
        instructions: "Restore upper flow path",
        timeThreshold: 33,
        subSteps: []
      },
      {
        id: 34,
        stepNumber: 12,
        title: "Open lower isolation",
        description: "Open lower isolation valve",
        instructions: "Restore lower flow path",
        timeThreshold: 13,
        subSteps: []
      },
      {
        id: 35,
        stepNumber: 13,
        title: "Monitor fluid rise",
        description: "Watch fluid levels and ILIC",
        instructions: "Observe system return to normal",
        timeThreshold: 69,
        subSteps: []
      },
      {
        id: 36,
        stepNumber: 14,
        title: "Verify normal operation",
        description: "Confirm system is operating normally",
        instructions: "Check all indicators and readings",
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
        id: 37,
        stepNumber: 1,
        title: "Prepare to start task",
        description: "Get ready to begin pressure testing",
        instructions: "Review procedure and safety requirements",
        timeThreshold: 137,
        subSteps: [
          {
            id: 38,
            stepNumber: 1,
            title: "Read procedure",
            description: "Review pressure testing procedure",
            instructions: "Carefully read all safety steps"
          },
          {
            id: 39,
            stepNumber: 2,
            title: "Gather safety equipment",
            description: "Collect necessary safety gear",
            instructions: "Get pressure-rated equipment"
          },
          {
            id: 40,
            stepNumber: 3,
            title: "Check workspace",
            description: "Ensure area is clear and safe",
            instructions: "Verify proper ventilation"
          }
        ]
      },
      {
        id: 41,
        stepNumber: 2,
        title: "Notify Control Room",
        description: "Inform control room of testing",
        instructions: "Communicate testing intentions",
        timeThreshold: 34,
        subSteps: []
      },
      {
        id: 42,
        stepNumber: 3,
        title: "Request Override/Bypass",
        description: "Ask CRO to place PST-113 in override",
        instructions: "Request system bypass for testing",
        timeThreshold: 104,
        subSteps: []
      },
      {
        id: 43,
        stepNumber: 4,
        title: "Close isolation valves",
        description: "Shut PST-113 isolation valves",
        instructions: "Ensure proper valve closure",
        timeThreshold: 111,
        subSteps: [
          {
            id: 49,
            stepNumber: 1,
            title: "Close upper isolation valve",
            description: "Shut the upper PST-113 isolation valve",
            instructions: "Turn valve handle clockwise to close",
            imageUrl: "/images/pressure/close_isolation.png"
          },
          {
            id: 50,
            stepNumber: 2,
            title: "Close lower isolation valve",
            description: "Shut the lower PST-113 isolation valve",
            instructions: "Turn valve handle clockwise to close"
          }
        ]
      },
      {
        id: 44,
        stepNumber: 5,
        title: "Check test connection",
        description: "Verify connection is depressurized",
        instructions: "Ensure safe testing conditions",
        timeThreshold: 124,
        subSteps: [
          {
            id: 51,
            stepNumber: 1,
            title: "Verify depressurization",
            description: "Check that connection is fully depressurized",
            instructions: "Use pressure gauge to confirm zero pressure"
          },
          {
            id: 52,
            stepNumber: 2,
            title: "Inspect connection point",
            description: "Examine the test connection for safety",
            instructions: "Ensure no leaks or obstructions",
            imageUrl: "/images/pressure/close_vent.png"
          },
          {
            id: 53,
            stepNumber: 3,
            title: "Confirm safe conditions",
            description: "Verify all safety requirements are met",
            instructions: "Double-check pressure readings and connections"
          }
        ]
      },
      {
        id: 45,
        stepNumber: 6,
        title: "Connect pressure source",
        description: "Attach external pressure testing source",
        instructions: "Connect test equipment properly",
        timeThreshold: 398,
        subSteps: [
          {
            id: 46,
            stepNumber: 1,
            title: "Check test equipment",
            description: "Verify pressure source is ready",
            instructions: "Inspect hoses and connections"
          },
          {
            id: 47,
            stepNumber: 2,
            title: "Connect test hose",
            description: "Attach pressure testing hose",
            instructions: "Ensure proper connection",
            imageUrl: "/images/pressure/reinstall_plug.png"
          },
          {
            id: 48,
            stepNumber: 3,
            title: "Verify connections",
            description: "Check all connections are secure",
            instructions: "Test for leaks"
          },
          {
            id: 49,
            stepNumber: 4,
            title: "Prepare pressure control",
            description: "Set up pressure control system",
            instructions: "Check pressure gauges"
          }
        ]
      },
      {
        id: 50,
        stepNumber: 7,
        title: "Increase test pressure",
        description: "Raise pressure until PSH trips",
        instructions: "Monitor pressure levels carefully",
        timeThreshold: 221,
        subSteps: []
      },
      {
        id: 51,
        stepNumber: 8,
        title: "Reduce pressure for PSH reset",
        description: "Lower pressure to reset PSH",
        instructions: "Adjust pressure gradually",
        timeThreshold: 66,
        subSteps: []
      },
      {
        id: 52,
        stepNumber: 9,
        title: "Reduce pressure for PSL trip",
        description: "Lower pressure until PSL trips",
        instructions: "Monitor low pressure switch",
        timeThreshold: 32,
        subSteps: []
      },
      {
        id: 53,
        stepNumber: 10,
        title: "Reduce pressure completely",
        description: "Release all test pressure",
        instructions: "Return to atmospheric pressure",
        timeThreshold: 170,
        subSteps: []
      },
      {
        id: 54,
        stepNumber: 11,
        title: "Disconnect test source",
        description: "Remove external pressure source",
        instructions: "Close test valve if required",
        timeThreshold: 33,
        subSteps: []
      },
      {
        id: 55,
        stepNumber: 12,
        title: "Open isolation valve",
        description: "Restore PST-113 isolation valve",
        instructions: "Return system to normal operation",
        timeThreshold: 24,
        subSteps: []
      },
      {
        id: 56,
        stepNumber: 13,
        title: "Verify pressure limits",
        description: "Check pressure within safe limits",
        instructions: "Confirm normal operating pressure",
        timeThreshold: 27,
        subSteps: []
      },
      {
        id: 57,
        stepNumber: 14,
        title: "Remove Override/Bypass",
        description: "Return system to normal control",
        instructions: "Restore automatic operation",
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
  if (proc.id === 1) { // Centrifuge procedure
    // Customize step 1 for Train 2
    cloned.steps = cloned.steps.map(step => {
      if (step.stepNumber === 1) {
        return {
          ...step,
          title: "Prepare to start task - Train 2",
          description: "Get ready to begin centrifuge testing on Train 2",
          instructions: "Gather Train 2 specific equipment: centrifuge tubes, heater unit B, and enhanced safety gear",
          timeThreshold: 60, // Different threshold for Train 2 (was 43 for Train 1)
          subSteps: [
            {
              id: 159, // Different ID to avoid conflicts
              stepNumber: 1,
              title: "Review Train 2 procedure",
              description: "Read through the Train 2 centrifuge testing procedure",
              instructions: "Familiarize yourself with Train 2 specific steps and safety protocols"
            },
            {
              id: 160,
              stepNumber: 2,
              title: "Gather Train 2 equipment",
              description: "Collect Train 2 specific testing equipment",
              instructions: "Get Train 2 centrifuge tubes, heater unit B, and enhanced safety gear",
              imageUrl: "/images/centrifuge/prepare.png"
            },
            {
              id: 161,
              stepNumber: 3,
              title: "Check Train 2 workspace",
              description: "Ensure Train 2 workspace is clean and organized",
              instructions: "Clear area, verify proper lighting, and check Train 2 specific safety requirements"
            },
            {
              id: 162,
              stepNumber: 4,
              title: "Verify Train 2 system status",
              description: "Check Train 2 system is ready",
              instructions: "Confirm Train 2 centrifuge and heater are operational"
            }
          ]
        };
      }
      return step; // Keep all other steps unchanged
    });
  }
  
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
