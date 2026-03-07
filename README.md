# XANES spectrum prediction using neural network models

 Currently, the models we provide are OmniXAS models of 3d transition metal (Ti-Cu) K-edge at two levels of theory: FEFF model for all the 8 elements and VASP models for Ti and Cu only. We recommend users of Lightshowai to cite the following references: Benchmark [Phys. Rev. Materials 8, 013801 (2024)], Lightshow [Journal of Open Source Software 8 (87), 5182 (2023)], and OmniXAS [Phys. Rev. Materials 9, 043803 (2025)]. Please contact Deyu Lu (dlu@bnl.gov) if you have questions.

> [!WARNING]
> This feature is a work in progress! Expect breaking changes!

Using [machine-learned neural networks](https://doi.org/10.48550/arXiv.2409.19552) stacked on top of the [M3GNet architecture](https://github.com/materialsvirtuallab/m3gnet), we have built in direct XANES spectrum prediction. 

# Installation
The cmake tool is needed for some OS/Python combinations by the BoltzTraP2 package.
On Ubuntu, please install it by:
```
sudo apt-get update
sudo apt-get install -y cmake build-essential
```
On RHEL/CentOS/Alma/Rocky:
```
sudo yum install -y cmake gcc gcc-c++ make
```

After cmake is installed, you can proceed to install LightshowAI by:
```bash
conda create -n LightshowAI python=3.11
conda activate LightshowAI
git clone git@github.com:AI-multimodal/LightshowAI.git LightshowAI
cd LightshowAI
pip install -e .
```

A web service is currently running at [Brookhaven National Lab](https://lightshowai.bnl.gov/)

# Run web service locally
Type in ```xas_ui``` after the conda environment is activated. You can run the command anywhere and don't have to be in the source code directory.


# Funding acknowledgment
This research is based upon work supported by the U.S. Department of Energy, Office of Science, Office Basic Energy Sciences, under Award Number FWP PS-030. This research used the Theory and Computation resources of the Center for Functional Nanomaterials (CFN), which is a U.S. Department of Energy Office of Science User Facility, at Brookhaven National Laboratory under Contract No. DE-SC0012704. The Software resulted from work developed under a U.S. Government Contract No. DE-SC0012704 and are subject to the following terms: the U.S. Government is granted for itself and others acting on its behalf a paid-up, nonexclusive, irrevocable worldwide license in this computer software and data to reproduce, prepare derivative works, and perform publicly and display publicly.

# BSD 3-Clause License
THE SOFTWARE IS SUPPLIED "AS IS" WITHOUT WARRANTY OF ANY KIND. THE UNITED STATES, THE UNITED STATES DEPARTMENT OF ENERGY, AND THEIR EMPLOYEES: (1) DISCLAIM ANY WARRANTIES, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO ANY IMPLIED WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE, TITLE OR NON-INFRINGEMENT, (2) DO NOT ASSUME ANY LEGAL LIABILITY OR RESPONSIBILITY FOR THE ACCURACY, COMPLETENESS, OR USEFULNESS OF THE SOFTWARE, (3) DO NOT REPRESENT THAT USE OF THE SOFTWARE WOULD NOT INFRINGE PRIVATELY OWNED RIGHTS, (4) DO NOT WARRANT THAT THE SOFTWARE WILL FUNCTION UNINTERRUPTED, THAT IT IS ERROR-FREE OR THAT ANY ERRORS WILL BE CORRECTED. IN NO EVENT SHALL THE UNITED STATES, THE UNITED STATES DEPARTMENT OF ENERGY, OR THEIR EMPLOYEES BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, CONSEQUENTIAL, SPECIAL OR PUNITIVE DAMAGES OF ANY KIND OR NATURE RESULTING FROM EXERCISE OF THIS LICENSE AGREEMENT OR THE USE OF THE SOFTWARE.