"""===========================================================================================================================================================================
Title:          ENERGY-CARBON OPTIMIZATION PLATFORM
Created:        October-2021
Authors:        Alissa Ganter (aganter@ethz.ch)
                Jacob Mannhardt (jmannhardt@ethz.ch)
Organization:   Laboratory of Risk and Reliability Engineering, ETH Zurich

Description:    Class defining the parameters, variables and constraints that hold for all technologies.
                The class takes the abstract optimization model as an input, and returns the parameters, variables and
                constraints that hold for all technologies.
==========================================================================================================================================================================="""

import logging
import sys
import pyomo.environ as pe
import pyomo.gdp as pgdp
import numpy as np
from model.objects.element import Element
from model.objects.energy_system import EnergySystem

class Technology(Element):
    # empty list of elements
    listOfElements = []

    def __init__(self, technology):
        """init generic technology object
        :param object: object of the abstract optimization model
        :param technology: technology that is added to the model"""

        logging.info('initialize object of a generic technology')
        super().__init__(technology)
        # store input data
        self.storeInputData()
        # add Technology to list
        Technology.addElement(self)

    def storeInputData(self):
        """ retrieves and stores input data for element as attributes. Each Child class overwrites method to store different attributes """
        # get system information
        system              = EnergySystem.getSystem()
        paths               = EnergySystem.getPaths()
        technologyTypes     = EnergySystem.getAnalysis()['subsets']["setTechnologies"]
        # set attributes of technology
        for technologyType in technologyTypes:
            if self.name in system[technologyType]:
                _inputPath                      = paths[technologyType][self.name]["folder"]
                self.setTimeStepsInvest         = self.dataInput.extractTimeSteps(_inputPath,typeOfTimeSteps="invest")
                self.setTimeStepsOperation      = self.dataInput.extractTimeSteps(_inputPath,typeOfTimeSteps="operation")
                self.timeStepsInvestDuration    = EnergySystem.calculateTimeStepDuration(self.setTimeStepsInvest)
                self.timeStepsOperationDuration = EnergySystem.calculateTimeStepDuration(self.setTimeStepsOperation)
                self.referenceCarrier           = [self.dataInput.extractAttributeData(_inputPath,"referenceCarrier")]
                self.minBuiltCapacity           = self.dataInput.extractAttributeData(_inputPath,"minBuiltCapacity")
                self.maxBuiltCapacity           = self.dataInput.extractAttributeData(_inputPath,"maxBuiltCapacity")
                self.lifetime                   = self.dataInput.extractAttributeData(_inputPath,"lifetime")

    ### --- classmethods to construct sets, parameters, variables, and constraints, that correspond to Technology --- ###
    @classmethod
    def constructSets(cls):
        """ constructs the pe.Sets of the class <Technology> """
        # construct the pe.Sets of the class <Technology>
        model = EnergySystem.getConcreteModel()

        # conversion technologies
        model.setConversionTechnologies = pe.Set(
            initialize=EnergySystem.getAttribute("setConversionTechnologies"),
            doc='Set of conversion technologies. Subset: setTechnologies')
        # transport technologies
        model.setTransportTechnologies = pe.Set(
            initialize=EnergySystem.getAttribute("setTransportTechnologies"),
            doc='Set of transport technologies. Subset: setTechnologies')
        # storage technologies
        model.setStorageTechnologies = pe.Set(
            initialize=EnergySystem.getAttribute("setStorageTechnologies"),
            doc='Set of storage technologies. Subset: setTechnologies')
        # invest time steps
        model.setTimeStepsInvest = pe.Set(
            model.setTechnologies,
            initialize = cls.getAttributeOfAllElements("setTimeStepsInvest"),
            doc="Set of time steps in investment for all technologies. Dimensions: setTechnologies"
        )
        # operational time steps
        model.setTimeStepsOperation = pe.Set(
            model.setTechnologies,
            initialize = cls.getAttributeOfAllElements("setTimeStepsOperation"),
            doc="Set of time steps in operation for all technologies. Dimensions: setTechnologies"
        )
        # combined technology and location set
        # model.setTechnologyLocation = pe.Set(
        #     initialize = technologyLocationRule,
        #     doc = "Combined set of technologies and locations. Conversion technologies are paired with nodes, transport technologies are paired with edges"
        # )
        # reference carriers
        model.setReferenceCarriers = pe.Set(
            model.setTechnologies,
            initialize = cls.getAttributeOfAllElements("referenceCarrier"),
            doc = "set of all reference carriers correspondent to a technology. Dimensions: setTechnologies"
        )
        # add pe.Sets of the child classes
        for subclass in cls.getAllSubclasses():
            subclass.constructSets()

    @classmethod
    def constructParams(cls):
        """ constructs the pe.Params of the class <Technology> """
        # construct pe.Param of the class <Technology>
        model = EnergySystem.getConcreteModel()

        # invest time step duration
        model.timeStepsInvestDuration = pe.Param(
            cls.createCustomSet(["setTechnologies","setTimeStepsInvest"]),
            initialize = cls.getAttributeOfAllElements("timeStepsInvestDuration"),
            doc="Parameter which specifies the time step duration in investment for all technologies. Dimensions: setTechnologies, setTimeStepsInvest"
        )
        # operational time step duration
        model.timeStepsOperationDuration = pe.Param(
            cls.createCustomSet(["setTechnologies","setTimeStepsOperation"]),
            initialize = cls.getAttributeOfAllElements("timeStepsOperationDuration"),
            doc="Parameter which specifies the time step duration in operation for all technologies. Dimensions: setTechnologies, setTimeStepsInvest"
        )
        # minimum capacity
        model.minBuiltCapacity = pe.Param(
            model.setTechnologies,
            initialize = cls.getAttributeOfAllElements("minBuiltCapacity"),
            doc = 'Parameter which specifies the minimum technology size that can be installed. Dimensions: setTechnologies')
        # maximum capacity
        model.maxBuiltCapacity = pe.Param(
            model.setTechnologies,
            initialize = cls.getAttributeOfAllElements("maxBuiltCapacity"),
            doc = 'Parameter which specifies the maximum technology size that can be installed. Dimensions: setTechnologies')
        # lifetime
        model.lifetimeTechnology = pe.Param(
            model.setTechnologies,
            initialize = cls.getAttributeOfAllElements("lifetime"),
            doc = 'Parameter which specifies the lifetime of technology. Dimensions: setTechnologies')
        
        # availability of technologies
        model.availabilityTechnology = pe.Param(
            cls.createCustomSet(["setTechnologies","setLocation","setTimeStepsInvest"]),
            initialize = cls.getAttributeOfAllElements("availability"),
            doc = 'Parameter which specifies the availability of technologies. Dimensions: setTechnologies, setLocation, setTimeStepsInvest')
        
        # minimum load relative to capacity
        model.minLoad = pe.Param(
            cls.createCustomSet(["setTechnologies","setLocation","setTimeStepsOperation"]),
            initialize = cls.getAttributeOfAllElements("minLoad"),
            doc = 'Parameter which specifies the minimum load of technology relative to installed capacity. Dimensions:setTechnologies, setLocation, setTimeStepsOperation')
        # maximum load relative to capacity
        model.maxLoad = pe.Param(
            cls.createCustomSet(["setTechnologies","setLocation","setTimeStepsOperation"]),
            initialize = cls.getAttributeOfAllElements("maxLoad"),
            doc = 'Parameter which specifies the maximum load of technology relative to installed capacity. Dimensions:setTechnologies, setLocation, setTimeStepsOperation')
        # add pe.Param of the child classes
        for subclass in cls.getAllSubclasses():
            subclass.constructParams()

    @classmethod
    def constructVars(cls):
        """ constructs the pe.Vars of the class <Technology> """
        def capacityBounds(model,tech, loc, time):
            """ return bounds of capacity for bigM expression
            :param model: pe.ConcreteModel
            :param tech: tech index
            :return bounds: bounds of capacity"""
            ### TODO: if existing capacity, add existing capacity
            existingCapacity = 0
            maxBuiltCapacity = len(model.setTimeStepsInvest[tech])*model.maxBuiltCapacity[tech]
            maxAvailabilityTechnology = model.availabilityTechnology[tech,loc,time]
            boundCapacity = min(maxBuiltCapacity + existingCapacity,maxAvailabilityTechnology)
            bounds = (0,boundCapacity)
            return(bounds)

        model = EnergySystem.getConcreteModel()
        # construct pe.Vars of the class <Technology>
        # install technology
        model.installTechnology = pe.Var(
            cls.createCustomSet(["setTechnologies","setLocation","setTimeStepsInvest"]),
            domain = pe.Binary,
            doc = 'installment of a technology on edge i and time t. Dimensions: setTechnologies, setLocation, setTimeStepsInvest. Domain: Binary')
        # capacity technology
        model.capacity = pe.Var(
            cls.createCustomSet(["setTechnologies","setLocation","setTimeStepsInvest"]),
            domain = pe.NonNegativeReals,
            bounds = capacityBounds,
            doc = 'size of installed technology on edge i and time t. Dimensions: setTechnologies, setLocation, setTimeStepsInvest. Domain: NonNegativeReals')
        # builtCapacity technology
        model.builtCapacity = pe.Var(
            cls.createCustomSet(["setTechnologies","setLocation","setTimeStepsInvest"]),
            domain = pe.NonNegativeReals,
            doc = 'size of built technology on edge i and time t. Dimensions: setTechnologies, setLocation, setTimeStepsInvest. Domain: NonNegativeReals')
        # capex technology
        model.capex = pe.Var(
            cls.createCustomSet(["setTechnologies","setLocation","setTimeStepsInvest"]),
            domain = pe.NonNegativeReals,
            doc = 'capex for installing technology on edge i and time t. Dimensions: setTechnologies, setLocation, setTimeStepsInvest. Domain: NonNegativeReals')
        # total capex technology
        model.capexTotal = pe.Var(
            domain = pe.NonNegativeReals,
            doc = 'total capex for installing all technologies on all edges at all times. Domain: NonNegativeReals')

        # add pe.Vars of the child classes
        for subclass in cls.getAllSubclasses():
            subclass.constructVars()

    @classmethod
    def constructConstraints(cls):
        """ constructs the pe.Constraints of the class <Technology> """
        model = EnergySystem.getConcreteModel()
        # construct pe.Constraints of the class <Technology>
        #  technology availability
        model.constraintTechnologyAvailability = pe.Constraint(
            cls.createCustomSet(["setTechnologies","setLocation","setTimeStepsInvest"]),
            rule = constraintTechnologyAvailabilityRule,
            doc = 'limited availability of  technology depending on node and time. Dimensions: setTechnologies, setLocation, setTimeStepsInvest'
        )
        # minimum capacity
        model.constraintTechnologyMinCapacity = pe.Constraint(
            cls.createCustomSet(["setTechnologies","setLocation","setTimeStepsInvest"]),
            rule = constraintTechnologyMinCapacityRule,
            doc = 'min capacity of technology that can be installed. Dimensions: setTechnologies, setLocation, setTimeStepsInvest'
        )
        # maximum capacity
        model.constraintTechnologyMaxCapacity = pe.Constraint(
            cls.createCustomSet(["setTechnologies","setLocation","setTimeStepsInvest"]),
            rule = constraintTechnologyMaxCapacityRule,
            doc = 'max capacity of technology that can be installed. Dimensions: setTechnologies, setLocation, setTimeStepsInvest'
        )

        # lifetime
        model.constraintTechnologyLifetime = pe.Constraint(
            cls.createCustomSet(["setTechnologies","setLocation","setTimeStepsInvest"]),
            rule = constraintTechnologyLifetimeRule,
            doc = 'max capacity of  technology that can be installed. Dimensions: setTechnologies, setLocation, setTimeStepsInvest'
        )
        # total capex of all technologies
        model.constraintCapexTotal = pe.Constraint(
            rule = constraintCapexTotalRule,
            doc = 'total capex of all technology that can be installed.'
        )
        # limit max load by installed capacity
        model.constraintMaxLoad = pe.Constraint(
            cls.createCustomSet(["setTechnologies","setLocation","setTimeStepsOperation"]),
            rule = constraintMaxLoadRule,
            doc = 'limit max load by installed capacity. Dimensions: setTechnologies, setLocation, setTimeStepsOperation'
        )
        # disjunct if technology is on
        model.disjunctOnTechnology = pgdp.Disjunct(
            cls.createCustomSet(["setTechnologies","setLocation","setTimeStepsOperation"]),
            rule = cls.disjunctOnTechnologyRule,
            doc = "disjunct to indicate that technology is On. Dimensions: setTechnologies, setLocation, setTimeStepsOperation"
        )
        # disjunct if technology is off
        model.disjunctOffTechnology = pgdp.Disjunct(
            cls.createCustomSet(["setTechnologies","setLocation","setTimeStepsOperation"]),
            rule = cls.disjunctOffTechnologyRule,
            doc = "disjunct to indicate that technology is off. Dimensions: setTechnologies, setLocation, setTimeStepsOperation"
        )
        # disjunction
        model.disjunctionDecisionOnOffTechnology = pgdp.Disjunction(
            cls.createCustomSet(["setTechnologies","setLocation","setTimeStepsOperation"]),
            rule = cls.expressionLinkDisjunctsRule,
            doc = "disjunction to link the on off disjuncts. Dimensions: setTechnologyLocation, setTimeStep")

        # add pe.Constraints of the child classes
        for subclass in cls.getAllSubclasses():
            subclass.constructConstraints()

    @classmethod
    def disjunctOnTechnologyRule(cls,disjunct, tech, loc, time):
        """definition of disjunct constraints if technology is On
        iterate through all subclasses to find corresponding implementation of disjunct constraints """
        for subclass in cls.getAllSubclasses():
            if tech in subclass.getAllNamesOfElements():
                # disjunct is defined in corresponding subclass
                subclass.disjunctOnTechnologyRule(disjunct,tech,loc,time)
                break

    @classmethod
    def disjunctOffTechnologyRule(cls,disjunct, tech, loc, time):
        """definition of disjunct constraints if technology is off
        iterate through all subclasses to find corresponding implementation of disjunct constraints """
        for subclass in cls.getAllSubclasses():
            if tech in subclass.getAllNamesOfElements():
                # disjunct is defined in corresponding subclass
                subclass.disjunctOffTechnologyRule(disjunct,tech,loc,time)
                break

    @classmethod
    def expressionLinkDisjunctsRule(cls,model, tech, loc, time):
        """ link disjuncts for technology is on and technology is off """
        return ([model.disjunctOnTechnology[tech,loc,time],model.disjunctOffTechnology[tech,loc,time]])

# function to combine the technologies and locations
def technologyLocationRule(model):
    """ creates list for setTechnologyLocation, where ConversionTechnologies are paired with the nodes and TransportTechnologies are paired with edges
    :return technologyLocationList: list of 2-tuple with (technology, location)"""
    technologyLocationList = [(technology,location) for technology in model.setConversionTechnologies for location in model.setNodes]
    technologyLocationList.extend([(technology,location) for technology in model.setTransportTechnologies for location in model.setEdges])
    return technologyLocationList

### --- constraint rules --- ###
#%% Constraint rules pre-defined in Technology class
def constraintTechnologyAvailabilityRule(model, tech, location, time):
    """limited availability of  technology"""
    if model.availabilityTechnology[tech, location, time] != np.inf:
        return (model.availabilityTechnology[tech, location, time] >= model.capacity[tech, location, time])
    else:
        return pe.Constraint.Skip

def constraintTechnologyMinCapacityRule(model, tech, location, time):
    """ min capacity expansion of  technology."""
    if model.minBuiltCapacity[tech] != 0:
        return (model.minBuiltCapacity[tech] * model.installTechnology[tech, location, time] <= model.builtCapacity[tech, location, time])
    else:
        return pe.Constraint.Skip

def constraintTechnologyMaxCapacityRule(model, tech, location, time):
    """max capacity expansion of  technology"""
    if model.maxBuiltCapacity[tech] != np.inf and tech not in model.setNLCapexTechs:
        return (model.maxBuiltCapacity[tech] * model.installTechnology[tech, location, time] >= model.builtCapacity[tech, location, time])
    else:
        return pe.Constraint.Skip

def constraintTechnologyLifetimeRule(model, tech, location, time):
    """limited lifetime of the technologies"""
    if tech not in model.setNLCapexTechs:
        # time range
        t_start = int(max(1, time - model.lifetimeTechnology[tech] + 1))
        t_end = time + 1

        return (model.capacity[tech, location, time]
                == sum(model.builtCapacity[tech,location, previousTime] for previousTime in range(t_start, t_end)))
    else:
        return pe.Constraint.Skip

def constraintCapexTotalRule(model):
    """ sums over all technologies to calculate total capex """
    return(model.capexTotal ==
        sum(
            sum(
                model.capex[tech, loc, time]
                for time in model.setTimeStepsInvest[tech]
            )
            for tech,loc in Element.createCustomSet(["setTechnologies","setLocation"])
        )
    )

def constraintMaxLoadRule(model, tech, loc, time):
    """Load is limited by the installed capacity and the maximum load factor"""
    referenceCarrier = model.setReferenceCarriers[tech][1]
    # get invest time step
    baseTimeStep = EnergySystem.decodeTimeStep(tech,time,"operation")
    investTimeStep = EnergySystem.encodeTimeStep(tech,baseTimeStep,"invest")
    # conversion technology
    if tech in model.setConversionTechnologies:
        if referenceCarrier in model.setInputCarriers[tech]:
            return (model.capacity[tech, loc, investTimeStep]*model.maxLoad[tech, loc, time] >= model.inputFlow[tech, referenceCarrier, loc, time])
        else:
            return (model.capacity[tech, loc, investTimeStep]*model.maxLoad[tech, loc, time] >= model.outputFlow[tech, referenceCarrier, loc, time])
    # transport technology
    elif tech in model.setTransportTechnologies:
            return (model.capacity[tech, loc, investTimeStep]*model.maxLoad[tech, loc, time] >= model.carrierFlow[tech, referenceCarrier, loc, time])
    else:
        logging.info(f"Technology {tech} is neither a conversion nor a transport technology. Constraint constraintMaxLoad skipped.")
        return pe.Constraint.Skip