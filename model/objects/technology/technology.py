"""===========================================================================================================================================================================
Title:          ZEN-GARDEN
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
    # set label
    label           = "setTechnologies"
    locationType    = None
    # empty list of elements
    listOfElements = []

    def __init__(self, technology):
        """init generic technology object
        :param object: object of the abstract optimization model
        :param technology: technology that is added to the model"""

        super().__init__(technology)
        # add Technology to list
        Technology.addElement(self)

    def storeInputData(self):
        """ retrieves and stores input data for element as attributes. Each Child class overwrites method to store different attributes """
        # set attributes of technology
        _setLocation    = type(self).getClassLocationType()

        setBaseTimeStepsYearly          = EnergySystem.getEnergySystem().setBaseTimeStepsYearly
        self.setTimeStepsInvest         = self.dataInput.extractTimeSteps(self.name,typeOfTimeSteps="invest")
        self.timeStepsInvestDuration    = EnergySystem.calculateTimeStepDuration(self.setTimeStepsInvest)
        self.sequenceTimeStepsInvest    = np.concatenate([[timeStep]*self.timeStepsInvestDuration[timeStep] for timeStep in self.timeStepsInvestDuration])
        EnergySystem.setSequenceTimeSteps(self.name,self.sequenceTimeStepsInvest,timeStepType="invest")


        self.referenceCarrier           = [self.dataInput.extractAttributeData("referenceCarrier",skipWarning=True)]
        EnergySystem.setTechnologyOfCarrier(self.name, self.referenceCarrier)
        self.minBuiltCapacity           = self.dataInput.extractAttributeData("minBuiltCapacity")["value"]
        self.maxBuiltCapacity           = self.dataInput.extractAttributeData("maxBuiltCapacity")["value"]
        self.lifetime                   = self.dataInput.extractAttributeData("lifetime")["value"]
        # add all raw time series to dict
        self.rawTimeSeries = {}
        self.rawTimeSeries["minLoad"]   = self.dataInput.extractInputData(
            "minLoad",indexSets=[_setLocation, "setTimeSteps"],timeSteps=setBaseTimeStepsYearly)
        self.rawTimeSeries["maxLoad"]   = self.dataInput.extractInputData(
            "maxLoad",indexSets=[_setLocation, "setTimeSteps"],timeSteps=setBaseTimeStepsYearly)
        self.rawTimeSeries["opexSpecific"] = self.dataInput.extractInputData(
            "opexSpecific",indexSets=[_setLocation,"setTimeSteps"],timeSteps=setBaseTimeStepsYearly)
        # non-time series input data
        self.capacityLimit              = self.dataInput.extractInputData("capacityLimit",indexSets=[_setLocation])
        self.carbonIntensityTechnology  = self.dataInput.extractInputData("carbonIntensity",indexSets=[_setLocation])
        # extract existing capacity
        self.setExistingTechnologies    = self.dataInput.extractSetExistingTechnologies()
        self.existingCapacity           = self.dataInput.extractInputData(
            "existingCapacity",indexSets=[_setLocation,"setExistingTechnologies"])
        self.lifetimeExistingTechnology = self.dataInput.extractLifetimeExistingTechnology(
            "existingCapacity",indexSets=[_setLocation,"setExistingTechnologies"])

    def calculateCapexOfExistingCapacities(self,storageEnergy = False):
        """ this method calculates the annualized capex of the existing capacities """
        if storageEnergy:
            existingCapacities  = self.existingCapacityEnergy
        else:
            existingCapacities  = self.existingCapacity
        # TODO fix correlation between setExistingTechnologies and setTimeStepsInvest.
        #  At the moment the specificCapex is extracted for the id of the existing capacity... should be investTimeStep.at(1) however
        existingCapex       = existingCapacities.to_frame().apply(
            lambda _existingCapacity: self.calculateCapexOfSingleCapacity(_existingCapacity.squeeze(),_existingCapacity.name),axis=1)
        return existingCapex

    def calculateCapexOfSingleCapacity(self,*args):
        """ this method calculates the annualized capex of the existing capacities. Is implemented in child class """
        raise NotImplementedError

    def calculateFractionalAnnuity(self):
        """calculate fraction of annuity to depreciate investment"""
        system              = EnergySystem.getSystem()
        _discountRate       = EnergySystem.getAnalysis()["discountRate"]
        _lifetime           = self.lifetime
        _annuity            = (((1 + _discountRate) ** _lifetime) * _discountRate) / ((1 + _discountRate) ** _lifetime - 1)
        # only account for fraction of year
        _fractionOfYear     = system["unaggregatedTimeStepsPerYear"] / system["totalHoursPerYear"]
        _fractionalAnnuity  = _annuity * _fractionOfYear
        return _fractionalAnnuity

    def overwriteTimeSteps(self,baseTimeSteps):
        """ overwrites setTimeStepsInvest and setTimeStepsOperation """
        setTimeStepsInvest      = EnergySystem.encodeTimeStep(self.name,baseTimeSteps=baseTimeSteps,timeStepType="invest",yearly=True)
        setTimeStepsOperation   = EnergySystem.encodeTimeStep(self.name, baseTimeSteps=baseTimeSteps,timeStepType="operation",yearly=True)
        setattr(self,"setTimeStepsInvest",setTimeStepsInvest.squeeze().tolist())
        setattr(self, "setTimeStepsOperation", setTimeStepsOperation.squeeze().tolist())

    def addNewlyBuiltCapacityTech(self,builtCapacity,capex,baseTimeSteps):
        """ adds the newly built capacity to the existing capacity
        :param builtCapacity: pd.Series of newly built capacity of technology
        :param capex: pd.Series of capex of newly built capacity of technology
        :param baseTimeSteps: base time steps of current horizon step """
        system = EnergySystem.getSystem()
        # reduce lifetime of existing capacities and add new remaining lifetime
        self.lifetimeExistingTechnology             = (self.lifetimeExistingTechnology - system["intervalBetweenYears"]).clip(lower=0)
        # new capacity
        _investTimeSteps                            = EnergySystem.encodeTimeStep(self.name, baseTimeSteps, "invest", yearly=True)
        # TODO currently summed over all invest time steps, fix for #TS_investPerYear >1
        _newlyBuiltCapacity                         = builtCapacity[_investTimeSteps].sum(axis=1)
        _capex                                      = capex[_investTimeSteps].sum(axis=1)
        # if at least one value unequal to zero
        if not (_newlyBuiltCapacity == 0).all():
            # add new index to setExistingTechnologies
            indexNewTechnology                              = max(self.setExistingTechnologies) + 1
            self.setExistingTechnologies                    = np.append(self.setExistingTechnologies, indexNewTechnology)

            for typeCapacity in list(set(_newlyBuiltCapacity.index.get_level_values(0))):
            # add power
                if typeCapacity == "power":
                    _energyString = ""
                elif typeCapacity == "energy":
                    _energyString = "Energy"
                _existingCapacity       = getattr(self,"existingCapacity"+_energyString)
                _lifetimeTechnology     = getattr(self, "lifetimeExistingTechnology" + _energyString)
                _capexExistingCapacity  = getattr(self, "capexExistingCapacity" + _energyString)
                # add new existing capacity
                _existingCapacity                           = _existingCapacity.unstack()
                _existingCapacity[indexNewTechnology]       = _newlyBuiltCapacity.loc[typeCapacity]
                setattr(self,"existingCapacity"+_energyString,_existingCapacity.stack())
                # add new remaining lifetime
                _lifetimeTechnology                         = _lifetimeTechnology.unstack()
                _lifetimeTechnology[indexNewTechnology]     = self.lifetime
                setattr(self, "lifetimeExistingTechnology" + _energyString,_lifetimeTechnology.stack())
                # calculate capex of existing capacity
                _capexExistingCapacity                      = _capexExistingCapacity.unstack()
                _capexExistingCapacity[indexNewTechnology]  = _capex.loc[typeCapacity]
                setattr(self, "capexExistingCapacity" + _energyString,_capexExistingCapacity.stack())

    ### --- getter/setter classmethods
    @classmethod
    def getClassLocationType(cls):
        """ returns locationType of class """
        return cls.locationType

    ### --- classmethods
    @classmethod
    def getLifetimeRange(cls, tech,capacityType, time, timeStepType: str = None):
        """ returns lifetime range of technology. If timeStepType, then converts the yearly time step 'time' to timeStepType """
        if timeStepType:
            baseTimeSteps   = EnergySystem.decodeTimeStep(None, time, "yearly")
            investTimeStep  = EnergySystem.encodeTimeStep(tech, baseTimeSteps, timeStepType, yearly=True)
        else:
            investTimeStep  = time
        tStart, tEnd = cls.getStartEndTimeOfLifetime(tech,capacityType, investTimeStep)

        return range(tStart, tEnd + 1)

    @classmethod
    def getAvailableExistingQuantity(cls, tech,capacityType,loc, time,typeExistingQuantity, timeStepType: str = None):
        """ returns existing quantity of 'tech', that is still available at invest time step 'time'.
        Either capacity or capex.
        :param tech: name of technology
        :param capacityType: either power or energy
        :param loc: location (node or edge) of existing capacity
        :param time: current time
        :param idExistingCapacity: id of existing capacity
        :return existingQuantity: existing capacity or capex of existing capacity
        """
        if timeStepType:
            baseTimeSteps   = EnergySystem.decodeTimeStep(None, time, "yearly")
            investTimeStep  = EnergySystem.encodeTimeStep(tech, baseTimeSteps, timeStepType, yearly=True)
        else:
            investTimeStep  = time

        model               = EnergySystem.getConcreteModel()
        existingQuantity = 0
        if typeExistingQuantity == "capacity":
            existingVariable = model.existingCapacity
        elif typeExistingQuantity == "capex":
            existingVariable = model.capexExistingCapacity
        else:
            raise KeyError(f"Wrong type of existing quantity {typeExistingQuantity}")

        for idExistingCapacity in model.setExistingTechnologies[tech]:
            tStart  = cls.getStartEndTimeOfLifetime(tech,capacityType, investTimeStep, idExistingCapacity,loc)
            # if still available at first base time step, add to list
            if tStart == model.setBaseTimeSteps.at(1):
                existingQuantity += existingVariable[tech,capacityType, loc, idExistingCapacity]
        return existingQuantity

    @classmethod
    def getStartEndTimeOfLifetime(cls, tech,capacityType, investTimeStep, idExistingCapacity = None,loc = None):
        """ counts back the lifetime to get the start invest time step and returns startInvestTimeStep
        :param tech: name of technology
        :param capacityType: either power or energy
        :param investTimeStep: current investment time step
        :param idExistingCapacity: id of existing capacity
        :param loc: location (node or edge) of existing capacity
        :return startInvestTimeStep,endInvestTimeStep: start and end of lifetime in invest time step domain"""
        # get model and system
        model   = EnergySystem.getConcreteModel()
        system  = EnergySystem.getSystem()
        # get endInvestTimeStep
        if not isinstance(investTimeStep, np.ndarray):
            endInvestTimeStep = investTimeStep
        elif len(investTimeStep) == 1:
            endInvestTimeStep = investTimeStep[0]
        # if more than one investment time step
        else:
            endInvestTimeStep = investTimeStep[-1]
            investTimeStep = investTimeStep[0]
        # decode to base time steps
        baseTimeSteps = EnergySystem.decodeTimeStep(tech, investTimeStep, timeStepType="invest")
        baseTimeStep = baseTimeSteps[0]
        # convert lifetime to interval of base time steps
        if idExistingCapacity is None:
            lifetimeYearly = model.lifetimeTechnology[tech]
        else:
            lifetimeYearly = model.lifetimeExistingTechnology[tech,capacityType,loc,idExistingCapacity]
        baseLifetime =  lifetimeYearly / system["intervalBetweenYears"] * system["unaggregatedTimeStepsPerYear"]
        if int(baseLifetime) != baseLifetime:
            logging.warning(
                f"The lifetime of {tech} does not translate to an integer lifetime interval in the base time domain ({baseLifetime})")
        # if startBaseTimeStep is further in the past than first base time step, use first base time step
        startBaseTimeStep       = int(max(model.setBaseTimeSteps.at(1), baseTimeStep - baseLifetime + 1))
        # if lifetime of existing capacity, then only return the start base time step
        if idExistingCapacity is not None:
            return startBaseTimeStep
        startInvestTimeStep     = EnergySystem.encodeTimeStep(tech, startBaseTimeStep, timeStepType="invest", yearly=True)[0]

        return startInvestTimeStep, endInvestTimeStep

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
        # existing installed technologies
        model.setExistingTechnologies = pe.Set(
            model.setTechnologies,
            initialize=cls.getAttributeOfAllElements("setExistingTechnologies"),
            doc='Set of existing technologies. Subset: setTechnologies')
        # invest time steps
        model.setTimeStepsInvest = pe.Set(
            model.setTechnologies,
            initialize = cls.getAttributeOfAllElements("setTimeStepsInvest"),
            doc="Set of time steps in investment for all technologies. Dimensions: setTechnologies"
        )
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
            initialize = EnergySystem.initializeComponent(cls,"timeStepsInvestDuration",indexNames=["setTechnologies","setTimeStepsInvest"]).astype(int),
            doc="Parameter which specifies the time step duration in investment for all technologies. Dimensions: setTechnologies, setTimeStepsInvest"
        )
        # existing capacity
        model.existingCapacity = pe.Param(
            cls.createCustomSet(["setTechnologies","setCapacityTypes", "setLocation", "setExistingTechnologies"]),
            initialize=EnergySystem.initializeComponent(cls,"existingCapacity",indexNames=["setTechnologies","setCapacityTypes", "setLocation", "setExistingTechnologies"],capacityTypes=True),
            doc='Parameter which specifies the existing technology size. Dimensions: setTechnologies')

        # minimum capacity
        model.minBuiltCapacity = pe.Param(
            cls.createCustomSet(["setTechnologies","setCapacityTypes"]),
            initialize = EnergySystem.initializeComponent(cls,"minBuiltCapacity",capacityTypes=True),
            doc = 'Parameter which specifies the minimum technology size that can be installed. Dimensions: setTechnologies')
        # maximum capacity
        model.maxBuiltCapacity = pe.Param(
            cls.createCustomSet(["setTechnologies","setCapacityTypes"]),
            initialize = EnergySystem.initializeComponent(cls,"maxBuiltCapacity",capacityTypes=True),
            doc = 'Parameter which specifies the maximum technology size that can be installed. Dimensions: setTechnologies')
        # lifetime existing technologies # TODO check if something has to be changed in initializeComponent
        model.lifetimeExistingTechnology = pe.Param(
            cls.createCustomSet(["setTechnologies","setCapacityTypes", "setLocation", "setExistingTechnologies"]),
            initialize=EnergySystem.initializeComponent(cls,"lifetimeExistingTechnology",capacityTypes=True),
            doc='Parameter which specifies the remaining lifetime of an existing technology. Dimensions: setTechnologies')
        # lifetime existing technologies
        model.capexExistingCapacity = pe.Param(
            cls.createCustomSet(["setTechnologies","setCapacityTypes", "setLocation", "setExistingTechnologies"]),
            initialize=EnergySystem.initializeComponent(cls,"capexExistingCapacity",capacityTypes=True),
            doc='Parameter which specifies the annualized capex of an existing technology which still has to be paid. Dimensions: setTechnologies')
        # lifetime newly built technologies
        model.lifetimeTechnology = pe.Param(
            model.setTechnologies,
            initialize = EnergySystem.initializeComponent(cls,"lifetime"),
            doc = 'Parameter which specifies the lifetime of a newly built technology. Dimensions: setTechnologies')
        # capacityLimit of technologies
        model.capacityLimitTechnology = pe.Param(
            cls.createCustomSet(["setTechnologies","setCapacityTypes","setLocation"]),
            initialize = EnergySystem.initializeComponent(cls,"capacityLimit",capacityTypes=True),
            doc = 'Parameter which specifies the capacity limit of technologies. Dimensions: setTechnologies, setLocation')
        # minimum load relative to capacity
        model.minLoad = pe.Param(
            cls.createCustomSet(["setTechnologies","setCapacityTypes","setLocation","setTimeStepsOperation"]),
            initialize = EnergySystem.initializeComponent(cls,"minLoad",indexNames=["setTechnologies","setCapacityTypes","setLocation","setTimeStepsOperation"],capacityTypes=True),
            doc = 'Parameter which specifies the minimum load of technology relative to installed capacity. Dimensions:setTechnologies, setLocation, setTimeStepsOperation')
        # maximum load relative to capacity
        model.maxLoad = pe.Param(
            cls.createCustomSet(["setTechnologies","setCapacityTypes","setLocation","setTimeStepsOperation"]),
            initialize = EnergySystem.initializeComponent(cls,"maxLoad",indexNames=["setTechnologies","setCapacityTypes","setLocation","setTimeStepsOperation"],capacityTypes=True),
            doc = 'Parameter which specifies the maximum load of technology relative to installed capacity. Dimensions:setTechnologies, setLocation, setTimeStepsOperation')
        # specific opex
        model.opexSpecific = pe.Param(
            cls.createCustomSet(["setTechnologies","setLocation","setTimeStepsOperation"]),
            initialize = EnergySystem.initializeComponent(cls,"opexSpecific",indexNames=["setTechnologies","setLocation","setTimeStepsOperation"]),
            doc = 'Parameter which specifies the specific opex. Dimensions: setTechnologies, setLocation, setTimeStepsOperation'
        )
        # carbon intensity
        model.carbonIntensityTechnology = pe.Param(
            cls.createCustomSet(["setTechnologies","setLocation"]),
            initialize = EnergySystem.initializeComponent(cls,"carbonIntensityTechnology"),
            doc = 'Parameter which specifies the carbon intensity of each technology. Dimensions: setTechnologies, setLocation'
        )

        # add pe.Param of the child classes
        for subclass in cls.getAllSubclasses():
            subclass.constructParams()

    @classmethod
    def constructVars(cls):
        """ constructs the pe.Vars of the class <Technology> """
        def capacityBounds(model,tech,capacityType, loc, time):
            """ return bounds of capacity for bigM expression
            :param model: pe.ConcreteModel
            :param tech: tech index
            :return bounds: bounds of capacity"""
            # bounds only needed for Big-M formulation, thus if any technology is modeled with on-off behavior
            if tech in Technology.createCustomSet(["setTechnologies","setOnOff"]):
                system = EnergySystem.getSystem()
                existingCapacities = 0
                if capacityType == system["setCapacityTypes"][0]:
                    for id in model.setExistingTechnologies[tech]:
                        if (time - model.lifetimeExistingTechnology[tech, loc, id] + 1) <= 0:
                            existingCapacities += model.existingCapacity[tech, loc, id]

                    maxBuiltCapacity = len(model.setTimeStepsInvest[tech])*model.maxBuiltCapacity[tech]
                    maxCapacityLimitTechnology = model.capacityLimitTechnology[tech,loc]
                else:
                    for id in model.setExistingTechnologies[tech]:
                        if (time - model.lifetimeExistingTechnology[tech, loc, id] + 1) <= 0:
                            existingCapacities += model.existingCapacityEnergy[tech, loc, id]

                    maxBuiltCapacity = len(model.setTimeStepsInvest[tech]) * model.maxBuiltCapacityEnergy[tech]
                    maxCapacityLimitTechnology = model.capacityLimitTechnologyEnergy[tech, loc]
                boundCapacity = min(maxBuiltCapacity + existingCapacities,maxCapacityLimitTechnology)
                bounds = (0,boundCapacity)
                return(bounds)
            else:
                return(None,None)

        model = EnergySystem.getConcreteModel()
        # construct pe.Vars of the class <Technology>
        # install technology
        model.installTechnology = pe.Var(
            cls.createCustomSet(["setTechnologies","setCapacityTypes","setLocation","setTimeStepsInvest"]),
            domain = pe.Binary,
            doc = 'installment of a technology at location l and time t. Dimensions: setTechnologies,"setCapacityTypes", setLocation, setTimeStepsInvest. Domain: Binary')
        # capacity technology
        model.capacity = pe.Var(
            cls.createCustomSet(["setTechnologies","setCapacityTypes","setLocation","setTimeStepsInvest"]),
            domain = pe.NonNegativeReals,
            bounds = capacityBounds,
            doc = 'size of installed technology at location l and time t. Dimensions: setTechnologies,"setCapacityTypes", setLocation, setTimeStepsInvest. Domain: NonNegativeReals')
        # builtCapacity technology
        model.builtCapacity = pe.Var(
            cls.createCustomSet(["setTechnologies","setCapacityTypes","setLocation","setTimeStepsInvest"]),
            domain = pe.NonNegativeReals,
            doc = 'size of built technology at location l and time t. Dimensions: setTechnologies,"setCapacityTypes", setLocation, setTimeStepsInvest. Domain: NonNegativeReals')
        # capex technology
        model.capex = pe.Var(
            cls.createCustomSet(["setTechnologies","setCapacityTypes","setLocation","setTimeStepsInvest"]),
            domain = pe.NonNegativeReals,
            doc = 'capex for installing technology at location l and time t. Dimensions: setTechnologies,"setCapacityTypes", setLocation, setTimeStepsInvest. Domain: NonNegativeReals')
        # total capex technology
        model.capexTotal = pe.Var(
            model.setTimeStepsYearly,
            domain = pe.NonNegativeReals,
            doc = 'total capex for installing all technologies in all locations at all times. Domain: NonNegativeReals')
        # opex
        model.opex = pe.Var(
            cls.createCustomSet(["setTechnologies","setLocation","setTimeStepsOperation"]),
            domain = pe.NonNegativeReals,
            doc = "opex for operating technology at location l and time t. Dimensions: setTechnologies, setLocation, setTimeStepsOperation. Domain: NonNegativeReals"
        )
        # total opex
        model.opexTotal = pe.Var(
            model.setTimeStepsYearly,
            domain = pe.NonNegativeReals,
            doc = "total opex for operating technology at location l and time t. Dimensions: setTechnologies, setLocation, setTimeStepsOperation. Domain: NonNegativeReals"
        )
        # carbon emissions
        model.carbonEmissionsTechnology = pe.Var(
            cls.createCustomSet(["setTechnologies","setLocation","setTimeStepsOperation"]),
            domain = pe.NonNegativeReals,
            doc = "carbon emissions for operating technology at location l and time t. Dimensions: setTechnologies, setLocation, setTimeStepsOperation. Domain: NonNegativeReals"
        )
        # total carbon emissions technology
        model.carbonEmissionsTechnologyTotal = pe.Var(
            model.setTimeStepsYearly,
            domain=pe.NonNegativeReals,
            doc="total carbon emissions for operating technology at location l and time t. Domain: NonNegativeReals"
        )

        # add pe.Vars of the child classes
        for subclass in cls.getAllSubclasses():
            subclass.constructVars()

    @classmethod
    def constructConstraints(cls):
        """ constructs the pe.Constraints of the class <Technology> """
        model = EnergySystem.getConcreteModel()
        # construct pe.Constraints of the class <Technology>
        #  technology capacityLimit
        model.constraintTechnologyCapacityLimit = pe.Constraint(
            cls.createCustomSet(["setTechnologies","setCapacityTypes","setLocation","setTimeStepsInvest"]),
            rule = constraintTechnologyCapacityLimitRule,
            doc = 'limited capacity of  technology depending on loc and time. Dimensions: setTechnologies,"setCapacityTypes", setLocation, setTimeStepsInvest'
        )
        # minimum capacity
        model.constraintTechnologyMinCapacity = pe.Constraint(
            cls.createCustomSet(["setTechnologies","setCapacityTypes","setLocation","setTimeStepsInvest"]),
            rule = constraintTechnologyMinCapacityRule,
            doc = 'min capacity of technology that can be installed. Dimensions: setTechnologies,"setCapacityTypes", setLocation, setTimeStepsInvest'
        )
        # maximum capacity
        model.constraintTechnologyMaxCapacity = pe.Constraint(
            cls.createCustomSet(["setTechnologies","setCapacityTypes","setLocation","setTimeStepsInvest"]),
            rule = constraintTechnologyMaxCapacityRule,
            doc = 'max capacity of technology that can be installed. Dimensions: setTechnologies,"setCapacityTypes", setLocation, setTimeStepsInvest'
        )
        # lifetime
        model.constraintTechnologyLifetime = pe.Constraint(
            cls.createCustomSet(["setTechnologies","setCapacityTypes","setLocation","setTimeStepsInvest"]),
            rule = constraintTechnologyLifetimeRule,
            doc = 'max capacity of  technology that can be installed. Dimensions: setTechnologies,"setCapacityTypes", setLocation, setTimeStepsInvest'
        )
        # limit max load by installed capacity
        model.constraintMaxLoad = pe.Constraint(
            cls.createCustomSet(["setTechnologies","setCapacityTypes","setLocation","setTimeStepsOperation"]),
            rule = constraintMaxLoadRule,
            doc = 'limit max load by installed capacity. Dimensions: setTechnologies,"setCapacityTypes", setLocation, setTimeStepsOperation'
        )
        # total capex of all technologies
        model.constraintCapexTotal = pe.Constraint(
            model.setTimeStepsYearly,
            rule = constraintCapexTotalRule,
            doc = 'total capex of all technology that can be installed.'
        )
        # calculate opex
        model.constraintOpexTechnology = pe.Constraint(
            cls.createCustomSet(["setTechnologies","setLocation","setTimeStepsOperation"]),
            rule = constraintOpexTechnologyRule,
            doc = "opex for each technology at each location and time step"
        )
        # total opex of all technologies
        model.constraintOpexTotal = pe.Constraint(
            model.setTimeStepsYearly,
            rule = constraintOpexTotalRule,
            doc = 'total opex of all technology that are operated.'
        )
        # carbon emissions of technologies
        model.constraintCarbonEmissionsTechnology = pe.Constraint(
            cls.createCustomSet(["setTechnologies","setLocation","setTimeStepsOperation"]),
            rule = constraintCarbonEmissionsTechnologyRule,
            doc = "carbon emissions for each technology at each location and time step"
        )
        # total carbon emissions of technologies
        model.constraintCarbonEmissionsTechnologyTotal = pe.Constraint(
            model.setTimeStepsYearly,
            rule=constraintCarbonEmissionsTechnologyTotalRule,
            doc="total carbon emissions for each technology at each location and time step"
        )

        # disjunct if technology is on
        model.disjunctOnTechnology = pgdp.Disjunct(
            cls.createCustomSet(["setTechnologies","setOnOff","setLocation","setTimeStepsOperation"]),
            rule = cls.disjunctOnTechnologyRule,
            doc = "disjunct to indicate that technology is On. Dimensions: setTechnologies, setLocation, setTimeStepsOperation"
        )
        # disjunct if technology is off
        model.disjunctOffTechnology = pgdp.Disjunct(
            cls.createCustomSet(["setTechnologies","setOnOff","setLocation","setTimeStepsOperation"]),
            rule = cls.disjunctOffTechnologyRule,
            doc = "disjunct to indicate that technology is off. Dimensions: setTechnologies, setLocation, setTimeStepsOperation"
        )
        # disjunction
        model.disjunctionDecisionOnOffTechnology = pgdp.Disjunction(
            cls.createCustomSet(["setTechnologies","setOnOff","setLocation","setTimeStepsOperation"]),
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

### --- constraint rules --- ###
#%% Constraint rules pre-defined in Technology class
def constraintTechnologyCapacityLimitRule(model, tech,capacityType, loc, time):
    """limited capacityLimit of  technology"""
    if model.capacityLimitTechnology[tech,capacityType, loc] != np.inf:
        return (model.capacityLimitTechnology[tech,capacityType, loc] >= model.capacity[tech,capacityType, loc, time])
    else:
        return pe.Constraint.Skip

def constraintTechnologyMinCapacityRule(model, tech,capacityType, loc, time):
    """ min capacity expansion of  technology."""
    if model.minBuiltCapacity[tech,capacityType] != 0:
        return (model.minBuiltCapacity[tech,capacityType] * model.installTechnology[tech,capacityType, loc, time] <= model.builtCapacity[tech,capacityType, loc, time])
    else:
        return pe.Constraint.Skip

def constraintTechnologyMaxCapacityRule(model, tech,capacityType, loc, time):
    """max capacity expansion of  technology"""
    if model.maxBuiltCapacity[tech,capacityType] != np.inf and tech not in Technology.createCustomSet(["setTechnologies","setCapexNL"]):
        return (model.maxBuiltCapacity[tech,capacityType] >= model.builtCapacity[tech,capacityType, loc, time])
    else:
        return pe.Constraint.Skip

def constraintTechnologyLifetimeRule(model, tech,capacityType, loc, time):
    """limited lifetime of the technologies"""
    if tech not in Technology.createCustomSet(["setTechnologies","setCapexNL"]):
        # determine existing capacities
        existingCapacities = Technology.getAvailableExistingQuantity(tech,capacityType,loc,time,typeExistingQuantity="capacity")

        return (model.capacity[tech,capacityType, loc, time]
                == existingCapacities
                + sum(model.builtCapacity[tech,capacityType, loc, previousTime] for previousTime in Technology.getLifetimeRange(tech,capacityType,time)))
    else:
        return pe.Constraint.Skip

def constraintCapexTotalRule(model,year):
    """ sums over all technologies to calculate total capex """

    return(model.capexTotal[year] ==
        sum(
            sum(
                model.capex[tech,capacityType, loc, time]
                for time in Technology.getLifetimeRange(tech,capacityType, year, timeStepType="invest")
            )
            +
            Technology.getAvailableExistingQuantity(tech,capacityType, loc, year, typeExistingQuantity="capex",timeStepType="invest")
            for tech,capacityType,loc in Element.createCustomSet(["setTechnologies","setCapacityTypes","setLocation"])
        )
    )

def constraintOpexTechnologyRule(model,tech,loc,time):
    """ calculate opex of each technology"""
    referenceCarrier = model.setReferenceCarriers[tech].at(1)
    if tech in model.setConversionTechnologies:
        if referenceCarrier in model.setInputCarriers[tech]:
            referenceFlow = model.inputFlow[tech,referenceCarrier,loc,time]
        else:
            referenceFlow = model.outputFlow[tech,referenceCarrier,loc,time]
    elif tech in model.setTransportTechnologies:
        referenceFlow = model.carrierFlow[tech, loc, time]
    else:
        referenceFlow = model.carrierFlowCharge[tech,loc,time] + model.carrierFlowDischarge[tech,loc,time]
    return(model.opex[tech,loc,time] == model.opexSpecific[tech,loc,time]*referenceFlow)

def constraintCarbonEmissionsTechnologyRule(model,tech,loc,time):
    """ calculate carbon emissions of each technology"""
    referenceCarrier = model.setReferenceCarriers[tech].at(1)
    if tech in model.setConversionTechnologies:
        if referenceCarrier in model.setInputCarriers[tech]:
            referenceFlow = model.inputFlow[tech,referenceCarrier,loc,time]
        else:
            referenceFlow = model.outputFlow[tech,referenceCarrier,loc,time]
    elif tech in model.setTransportTechnologies:
        referenceFlow = model.carrierFlow[tech, loc, time]
    else:
        referenceFlow = model.carrierFlowCharge[tech,loc,time] + model.carrierFlowDischarge[tech,loc,time]
    return(model.carbonEmissionsTechnology[tech,loc,time] == model.carbonIntensityTechnology[tech,loc]*referenceFlow)

def constraintCarbonEmissionsTechnologyTotalRule(model, year):
    """ calculate total carbon emissions of each technology"""
    baseTimeStep = EnergySystem.decodeTimeStep(None,year,"yearly")
    return(
        model.carbonEmissionsTechnologyTotal[year] ==
        sum(
            sum(
                model.carbonEmissionsTechnology[tech,loc,time]*model.timeStepsOperationDuration[tech, time]
                for time in EnergySystem.encodeTimeStep(tech, baseTimeStep, "operation", yearly = True)
            )
            for tech, loc in Element.createCustomSet(["setTechnologies", "setLocation"])
        )
    )

def constraintOpexTotalRule(model,year):
    """ sums over all technologies to calculate total opex """
    baseTimeStep = EnergySystem.decodeTimeStep(None, year, "yearly")
    return(model.opexTotal[year] ==
        sum(
            sum(
                model.opex[tech, loc, time]*model.timeStepsOperationDuration[tech,time]
                for time in EnergySystem.encodeTimeStep(tech, baseTimeStep, "operation", yearly=True)
            )
            for tech,loc in Element.createCustomSet(["setTechnologies","setLocation"])
        )
    )

def constraintMaxLoadRule(model, tech,capacityType, loc, time):
    """Load is limited by the installed capacity and the maximum load factor"""
    referenceCarrier = model.setReferenceCarriers[tech].at(1)
    # get invest time step
    investTimeStep = EnergySystem.convertTechnologyTimeStepType(tech,time,"operation2invest")
    # conversion technology
    if tech in model.setConversionTechnologies:
        if referenceCarrier in model.setInputCarriers[tech]:
            return (model.capacity[tech,capacityType, loc, investTimeStep]*model.maxLoad[tech,capacityType, loc, time] >= model.inputFlow[tech, referenceCarrier, loc, time])
        else:
            return (model.capacity[tech,capacityType, loc, investTimeStep]*model.maxLoad[tech,capacityType, loc, time] >= model.outputFlow[tech, referenceCarrier, loc, time])
    # transport technology
    elif tech in model.setTransportTechnologies:
            return (model.capacity[tech,capacityType, loc, investTimeStep]*model.maxLoad[tech,capacityType, loc, time] >= model.carrierFlow[tech, loc, time])
    # storage technology
    elif tech in model.setStorageTechnologies:
        system = EnergySystem.getSystem()
        # if limit power
        if capacityType == system["setCapacityTypes"][0]:
            return (model.capacity[tech,capacityType, loc, investTimeStep]*model.maxLoad[tech,capacityType, loc, time] >= model.carrierFlowCharge[tech, loc, time] + model.carrierFlowDischarge[tech, loc, time])
        # TODO integrate level storage here as well
        else:
            return pe.Constraint.Skip
        # if limit energy
        # else:
        #     return (model.capacity[tech,capacityType, loc, investTimeStep] * model.maxLoad[tech,capacityType, loc, time] >= model.levelStorage[tech,loc,time])