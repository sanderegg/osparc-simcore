/* eslint no-warning-comments: "off" */
/* global window */

const BUTTON_SIZE = 50;
const BUTTON_SPACING = 10;

qx.Class.define("qxapp.components.workbench.Workbench", {
  extend: qx.ui.container.Composite,

  construct: function(workbenchData) {
    this.base();

    let canvas = new qx.ui.layout.Canvas();
    this.set({
      layout: canvas
    });

    this.__desktop = new qx.ui.window.Desktop(new qx.ui.window.Manager());
    this.add(this.__desktop, {
      left: 0,
      top: 0,
      right: 0,
      bottom: 0
    });

    this.__svgWidget = new qxapp.components.workbench.SvgWidget();
    // this gets fired once the widget has appeared and the library has been loaded
    // due to the qx rendering, this will always happen after setup, so we are
    // sure to catch this event
    if (workbenchData) {
      this.__svgWidget.addListenerOnce("SvgWidgetReady", () => {
        // Will be called only the first time Svg lib is loaded
        this.__loadProject(workbenchData);
      });
    }

    this.__desktop.add(this.__svgWidget, {
      left: 0,
      top: 0,
      right: 0,
      bottom: 0
    });

    this.__desktop.addListener("click", function(e) {
      this.__selectedItemChanged(null);
    }, this);

    this.__desktop.addListener("changeActiveWindow", function(e) {
      let winEmitting = e.getData();
      if (winEmitting && winEmitting.isActive() && winEmitting.classname.includes("workbench.Node")) {
        this.__selectedItemChanged(winEmitting.getNodeId());
      } else {
        this.__selectedItemChanged(null);
      }
    }, this);
    // TODO how about making the LoggerView a singleton then it could be accessed from anywhere
    this.__logger = new qxapp.components.workbench.logger.LoggerView();
    this.__desktop.add(this.__logger);

    this.__nodes = [];
    this.__nodeMap = {};
    this.__links = [];

    let loggerButton = this.__getShowLoggerButton();
    this.add(loggerButton, {
      left: 20,
      bottom: 20
    });

    let buttonContainer = new qx.ui.container.Composite(new qx.ui.layout.HBox(BUTTON_SPACING));
    this.add(buttonContainer, {
      bottom: 20,
      right: 20
    });
    [
      this.__getPlusButton(),
      this.__getRemoveButton(),
      this.__getPlayButton(),
      this.__getStopButton()
    ].forEach(widget => {
      buttonContainer.add(widget);
    });

    this.setCanStart(true);

    this.addListener("dblclick", function(pointerEvent) {
      // FIXME:
      const navBarHeight = 50;
      let x = pointerEvent.getViewportLeft() - this.getBounds().left;
      let y = pointerEvent.getViewportTop() - navBarHeight;

      let srvCat = new qxapp.components.workbench.servicesCatalogue.ServicesCatalogue();
      srvCat.moveTo(x, y);
      srvCat.open();
      let pos = {
        x: x,
        y: y
      };
      srvCat.addListener("AddService", function(e) {
        this.__addServiceFromCatalogue(e, pos);
      }, this);
    }, this);
  },

  events: {
    "NodeDoubleClicked": "qx.event.type.Data"
  },

  properties: {
    canStart: {
      nullable: false,
      init: true,
      check: "Boolean",
      apply : "__applyCanStart"
    }
  },

  members: {
    __nodes: null,
    __nodeMap: null,
    __links: null,
    __desktop: null,
    __svgWidget: null,
    __logger: null,
    __tempLinkNodeId: null,
    __tempLinkPortId: null,
    __tempLinkRepr: null,
    __pointerPosX: null,
    __pointerPosY: null,
    __selectedItemId: null,
    __playButton: null,
    __stopButton: null,

    getNode: function(nodeId) {
      return this.__nodeMap[nodeId];
    },
    __getShowLoggerButton: function() {
      const icon = "@FontAwesome5Solid/list-alt/32";
      let loggerButton = new qx.ui.form.Button(null, icon);
      loggerButton.set({
        width: BUTTON_SIZE,
        height: BUTTON_SIZE
      });
      loggerButton.addListener("execute", function() {
        const bounds = loggerButton.getBounds();
        loggerButton.hide();
        this.__logger.moveTo(bounds.left, bounds.top+bounds.height - this.__logger.getHeight());
        this.__logger.open();
        this.__logger.addListenerOnce("close", function() {
          loggerButton.show();
        }, this);
      }, this);
      return loggerButton;
    },

    __getPlusButton: function() {
      const icon = "@FontAwesome5Solid/plus/32"; // qxapp.dev.Placeholders.getIcon("fa-plus", 32);
      let plusButton = new qx.ui.form.Button(null, icon);
      plusButton.set({
        width: BUTTON_SIZE,
        height: BUTTON_SIZE
      });
      plusButton.addListener("execute", function() {
        let srvCat = new qxapp.components.workbench.servicesCatalogue.ServicesCatalogue();
        srvCat.moveTo(200, 200);
        srvCat.open();
        srvCat.addListener("AddService", function(e) {
          this.__addServiceFromCatalogue(e);
        }, this);
      }, this);
      return plusButton;
    },

    __getPlusMenuButton: function() {
      const icon = "@FontAwesome5Solid/plus/32"; // qxapp.dev.Placeholders.getIcon("fa-plus", 32);
      let plusButton = new qx.ui.form.MenuButton(null, icon, this.__getServicesMenu());
      plusButton.set({
        width: BUTTON_SIZE,
        height: BUTTON_SIZE
      });
      plusButton.addListener("execute", function() {
        plusButton.setMenu(this.__getServicesMenu());
      }, this);
      return plusButton;
    },

    __getServicesMenu: function() {
      let menuNodeTypes = new qx.ui.menu.Menu();

      let producersButton = new qx.ui.menu.Button("Producers", null, null, this.__getProducers());
      menuNodeTypes.add(producersButton);
      let computationalsButton = new qx.ui.menu.Button("Computationals", null, null, this.__getComputationals());
      menuNodeTypes.add(computationalsButton);
      let analysesButton = new qx.ui.menu.Button("Analyses", null, null, this.__getAnalyses());
      menuNodeTypes.add(analysesButton);

      return menuNodeTypes;
    },

    __getPlayButton: function() {
      const icon = "@FontAwesome5Solid/play/32";
      let playButton = this.__playButton = new qx.ui.form.Button(null, icon);
      playButton.set({
        width: BUTTON_SIZE,
        height: BUTTON_SIZE
      });

      playButton.addListener("execute", function() {
        if (this.getCanStart()) {
          this.__startPipeline();
        } else {
          this.__logger.info("Can not start pipeline");
        }
      }, this);

      return playButton;
    },

    __getStopButton: function() {
      const icon = "@FontAwesome5Solid/stop-circle/32";
      let stopButton = this.__stopButton = new qx.ui.form.Button(null, icon);
      stopButton.set({
        width: BUTTON_SIZE,
        height: BUTTON_SIZE
      });

      stopButton.addListener("execute", function() {
        this.__stopPipeline();
      }, this);
      return stopButton;
    },

    __applyCanStart: function(value, old) {
      if (value) {
        this.__playButton.setVisibility("visible");
        this.__stopButton.setVisibility("excluded");
      } else {
        this.__playButton.setVisibility("excluded");
        this.__stopButton.setVisibility("visible");
      }
    },

    __getRemoveButton: function() {
      const icon = "@FontAwesome5Solid/trash/32";
      let removeButton = new qx.ui.form.Button(null, icon);
      removeButton.set({
        width: BUTTON_SIZE,
        height: BUTTON_SIZE
      });
      removeButton.addListener("execute", function() {
        if (this.__selectedItemId && this.__isSelectedItemALink(this.__selectedItemId)) {
          this.__removeLink(this.__getLink(this.__selectedItemId));
          this.__selectedItemId = null;
        } else {
          this.__removeSelectedNode();
        }
      }, this);
      return removeButton;
    },

    __addServiceFromCatalogue: function(e, pos) {
      let data = e.getData();
      let nodeMetaData = data.service;
      let nodeAId = data.contextNodeId;
      let portA = data.contextPort;

      let nodeB = this.__createNode(nodeMetaData.imageId, null, nodeMetaData);
      this.__addNodeToWorkbench(nodeB, pos);

      if (nodeAId !== null && portA !== null) {
        let nodeBId = nodeB.getNodeId();
        let portB = this.__findCompatiblePort(nodeB, portA);
        // swap node-ports to have node1 as input and node2 as output
        if (portA.isInput) {
          [nodeAId, portA, nodeBId, portB] = [nodeBId, portB, nodeAId, portA];
        }
        this.__addLink({
          nodeUuid: nodeAId,
          output: portA.portId
        }, {
          nodeUuid: nodeBId,
          input: portB.portId
        });
      }
    },

    __createMenuFromList: function(nodesList) {
      let buttonsListMenu = new qx.ui.menu.Menu();

      nodesList.forEach(nodeMetaData => {
        let nodeButton = new qx.ui.menu.Button(nodeMetaData.label);
        nodeButton.addListener("execute", function() {
          let nodeItem = this.__createNode(nodeMetaData.imageId, null, nodeMetaData);
          this.__addNodeToWorkbench(nodeItem);
        }, this);

        buttonsListMenu.add(nodeButton);
      });

      return buttonsListMenu;
    },

    __createWindowForBuiltInService: function(widget, width, height, caption) {
      let serviceWindow = new qx.ui.window.Window();
      serviceWindow.set({
        showMinimize: false,
        showStatusbar: false,
        width: width,
        height: height,
        minWidth: 400,
        minHeight: 400,
        modal: true,
        caption: caption,
        layout: new qx.ui.layout.Canvas()
      });

      serviceWindow.add(widget, {
        left: 0,
        top: 0,
        right: 0,
        bottom: 0
      });

      serviceWindow.moveTo(100, 100);

      return serviceWindow;
    },

    __addNodeToWorkbench: function(node, position) {
      if (position === undefined || position === null) {
        let farthestRight = 0;
        for (let i=0; i < this.__nodes.length; i++) {
          let boundPos = this.__nodes[i].getBounds();
          let rightPos = boundPos.left + boundPos.width;
          if (farthestRight < rightPos) {
            farthestRight = rightPos;
          }
        }
        node.moveTo(50 + farthestRight, 200);
        this.addWindowToDesktop(node);
        this.__nodes.push(node);
      } else {
        node.moveTo(position.x, position.y);
        this.addWindowToDesktop(node);
        this.__nodes.push(node);
      }

      node.addListener("NodeMoving", function() {
        this.__updateLinks(node);
      }, this);

      node.addListener("appear", function() {
        this.__updateLinks(node);
      }, this);

      node.addListener("dblclick", function(e) {
        if (node.getMetaData().key.includes("FileManager")) {
          const width = 800;
          const height = 600;
          let fileManager = new qxapp.components.widgets.FileManager();
          let fileManagerWindow = this.__createWindowForBuiltInService(fileManager, width, height, "File Manager");
          fileManager.addListener("ItemSelected", function(data) {
            const itemPath = data.getData().itemPath;
            const splitted = itemPath.split("/");
            const itemName = splitted[splitted.length-1];
            const isDirectory = data.getData().isDirectory;
            const activePort = isDirectory ? "outDir" : "outFile";
            const inactivePort = isDirectory ? "outFile" : "outDir";
            node.getMetaData().outputs[activePort].value = itemPath;
            node.getMetaData().outputs[inactivePort].value = null;
            node.getOutputPorts(activePort).ui.setLabel(itemName);
            node.getOutputPorts(activePort).ui.getToolTip().setLabel(itemName);
            node.getOutputPorts(inactivePort).ui.setLabel("");
            node.getOutputPorts(inactivePort).ui.getToolTip().setLabel("");
            node.setProgress(100);
            fileManagerWindow.close();
          }, this);

          fileManagerWindow.moveTo(100, 100);
          fileManagerWindow.open();
        } else {
          this.fireDataEvent("NodeDoubleClicked", node);
        }
        e.stopPropagation();
      }, this);

      qx.ui.core.queue.Layout.flush();
    },

    __createNode: function(nodeImageId, uuid, nodeData) {
      let nodeBase = new qxapp.components.workbench.NodeBase(nodeImageId, uuid, nodeData);

      const evType = "pointermove";
      nodeBase.addListener("LinkDragStart", function(e) {
        let data = e.getData();
        let event = data.event;
        let dragNodeId = data.nodeId;
        let dragIsInput = data.isInput;
        let dragPortId = data.portId;

        // Register supported actions
        event.addAction("move");

        // Register supported types
        event.addType("osparc-metaData");
        let dragData = {
          dragNodeId: dragNodeId,
          dragIsInput: dragIsInput,
          dragPortId: dragPortId
        };
        event.addData("osparc-metaData", dragData);

        this.__tempLinkNodeId = dragData.dragNodeId;
        this.__tempLinkIsInput = dragData.dragIsInput;
        this.__tempLinkPortId = dragData.dragPortId;
        qx.bom.Element.addListener(
          this.__desktop,
          evType,
          this.__startTempLink,
          this
        );
      }, this);

      nodeBase.addListener("LinkDragOver", function(e) {
        let data = e.getData();
        let event = data.event;
        let dropNodeId = data.nodeId;
        let dropIsInput = data.isInput;
        let dropPortId = data.portId;

        let compatible = false;
        if (event.supportsType("osparc-metaData")) {
          const dragNodeId = event.getData("osparc-metaData").dragNodeId;
          const dragIsInput = event.getData("osparc-metaData").dragIsInput;
          const dragPortId = event.getData("osparc-metaData").dragPortId;
          const dragNode = this.__getNode(dragNodeId);
          const dropNode = this.__getNode(dropNodeId);
          const dragPortTarget = dragIsInput ? dragNode.getOutputPort(dragPortId) : dragNode.getInputPort(dragPortId);
          const dropPortTarget = dropIsInput ? dropNode.getOutputPort(dropPortId) : dropNode.getInputPort(dropPortId);
          compatible = this.__arePortsCompatible(dragPortTarget, dropPortTarget);
        }

        if (!compatible) {
          event.preventDefault();
        }
      }, this);

      nodeBase.addListener("LinkDrop", function(e) {
        let data = e.getData();
        let event = data.event;
        let dropNodeId = data.nodeId;
        let dropIsInput = data.isInput;
        let dropPortId = data.portId;

        if (event.supportsType("osparc-metaData")) {
          let dragNodeId = event.getData("osparc-metaData").dragNodeId;
          let dragIsInput = event.getData("osparc-metaData").dragIsInput;
          let dragPortId = event.getData("osparc-metaData").dragPortId;

          let nodeAId = dropIsInput ? dragNodeId : dropNodeId;
          let nodeAPortId = dropIsInput ? dragPortId : dropPortId;
          let nodeBId = dragIsInput ? dragNodeId : dropNodeId;
          let nodeBPortId = dragIsInput ? dragPortId : dropPortId;

          this.__addLink({
            nodeUuid: nodeAId,
            output: nodeAPortId
          }, {
            nodeUuid: nodeBId,
            input: nodeBPortId
          });
          this.__removeTempLink();
          qx.bom.Element.removeListener(
            this.__desktop,
            evType,
            this.__startTempLink,
            this
          );
        }
      }, this);

      nodeBase.addListener("LinkDragEnd", function(e) {
        let data = e.getData();
        // let event = data.event"];
        let dragNodeId = data.nodeId;
        let dragPortId = data.portId;

        let posX = this.__pointerPosX;
        let posY = this.__pointerPosY;
        if (this.__tempLinkNodeId === dragNodeId && this.__tempLinkPortId === dragPortId) {
          let srvCat = new qxapp.components.workbench.servicesCatalogue.ServicesCatalogue();
          if (this.__tempLinkIsInput === true) {
            srvCat.setContext(dragNodeId, this.__getNode(dragNodeId).getInputPort(dragPortId));
          } else {
            srvCat.setContext(dragNodeId, this.__getNode(dragNodeId).getOutputPort(dragPortId));
          }
          srvCat.moveTo(posX, posY);
          srvCat.open();
          let pos = {
            x: posX,
            y: posY
          };
          srvCat.addListener("AddService", function(ev) {
            this.__addServiceFromCatalogue(ev, pos);
          }, this);
          srvCat.addListener("close", function(ev) {
            this.__removeTempLink();
          }, this);
        }
        qx.bom.Element.removeListener(
          this.__desktop,
          evType,
          this.__startTempLink,
          this
        );
      }, this);

      return nodeBase;
    },

    __removeSelectedNode: function() {
      for (let i=0; i<this.__nodes.length; i++) {
        if (this.__desktop.getActiveWindow() === this.__nodes[i]) {
          let connectedLinks = this.__getConnectedLinks(this.__nodes[i].getNodeId());
          for (let j=0; j<connectedLinks.length; j++) {
            this.__removeLink(this.__getLink(connectedLinks[j]));
          }
          this.__removeNode(this.__nodes[i]);
          return;
        }
      }
    },

    __arePortsCompatible: function(port1, port2) {
      let compatible = (port1.portType === port2.portType);
      compatible = compatible && (port1.isInput !== port2.isInput);
      return compatible;
    },

    __findCompatiblePort: function(nodeB, portA) {
      if (portA.isInput) {
        for (let portBId in nodeB.getOutputPorts()) {
          let portB = nodeB.getOutputPorts()[portBId];
          if (portA.portType === portB.portType) {
            return portB;
          }
        }
      } else {
        for (let portBId in nodeB.getInputPorts()) {
          let portB = nodeB.getInputPort(portBId);
          if (portA.portType === portB.portType) {
            return portB;
          }
        }
      }
      return null;
    },

    __addLink: function(from, to, linkId) {
      let node1Id = from.nodeUuid;
      let port1Id = from.output;
      let node2Id = to.nodeUuid;
      let port2Id = to.input;

      let node1 = this.__getNode(node1Id);
      let port1 = node1.getOutputPort(port1Id);
      let node2 = this.__getNode(node2Id);
      let port2 = node2.getInputPort(port2Id);

      const pointList = this.__getLinkPoints(node1, port1, node2, port2);
      const x1 = pointList[0][0];
      const y1 = pointList[0][1];
      const x2 = pointList[1][0];
      const y2 = pointList[1][1];
      let linkRepresentation = this.__svgWidget.drawCurve(x1, y1, x2, y2);
      let linkBase = new qxapp.components.workbench.LinkBase(linkRepresentation);
      linkBase.setInputNodeId(node1.getNodeId());
      linkBase.setInputPortId(port1.portId);
      linkBase.setOutputNodeId(node2.getNodeId());
      linkBase.setOutputPortId(port2.portId);
      if (linkId !== undefined) {
        linkBase.setLinkId(linkId);
      }
      this.__links.push(linkBase);

      node2.getPropsWidget().enableProp(port2.portId, false);

      linkBase.getRepresentation().node.addEventListener("click", function(e) {
        // this is needed to get out of the context of svg
        linkBase.fireDataEvent("linkSelected", linkBase.getLinkId());
        e.stopPropagation();
      }, this);

      linkBase.addListener("linkSelected", function(e) {
        this.__selectedItemChanged(linkBase.getLinkId());
      }, this);

      return linkBase;
    },

    __updateLinks: function(node) {
      let linksInvolved = this.__getConnectedLinks(node.getNodeId());

      linksInvolved.forEach(linkId => {
        let link = this.__getLink(linkId);
        if (link) {
          let node1 = this.__getNode(link.getInputNodeId());
          let port1 = node1.getOutputPort(link.getInputPortId());
          let node2 = this.__getNode(link.getOutputNodeId());
          let port2 = node2.getInputPort(link.getOutputPortId());
          const pointList = this.__getLinkPoints(node1, port1, node2, port2);
          const x1 = pointList[0][0];
          const y1 = pointList[0][1];
          const x2 = pointList[1][0];
          const y2 = pointList[1][1];
          this.__svgWidget.updateCurve(link.getRepresentation(), x1, y1, x2, y2);
        }
      });
    },

    __startTempLink: function(pointerEvent) {
      if (this.__tempLinkNodeId === null || this.__tempLinkPortId === null) {
        return;
      }
      let node = this.__getNode(this.__tempLinkNodeId);
      if (node === null) {
        return;
      }
      let port;
      if (this.__tempLinkIsInput) {
        port = node.getInputPort(this.__tempLinkPortId);
      } else {
        port = node.getOutputPort(this.__tempLinkPortId);
      }
      if (port === null) {
        return;
      }

      let x1;
      let y1;
      let x2;
      let y2;
      const portPos = node.getLinkPoint(port);
      // FIXME:
      const navBarHeight = 50;
      this.__pointerPosX = pointerEvent.getViewportLeft() - this.getBounds().left;
      this.__pointerPosY = pointerEvent.getViewportTop() - navBarHeight;

      if (port.isInput) {
        x1 = this.__pointerPosX;
        y1 = this.__pointerPosY;
        x2 = portPos[0];
        y2 = portPos[1];
      } else {
        x1 = portPos[0];
        y1 = portPos[1];
        x2 = this.__pointerPosX;
        y2 = this.__pointerPosY;
      }

      if (this.__tempLinkRepr === null) {
        this.__tempLinkRepr = this.__svgWidget.drawCurve(x1, y1, x2, y2);
      } else {
        this.__svgWidget.updateCurve(this.__tempLinkRepr, x1, y1, x2, y2);
      }
    },

    __removeTempLink: function() {
      if (this.__tempLinkRepr !== null) {
        this.__svgWidget.removeCurve(this.__tempLinkRepr);
      }
      this.__tempLinkRepr = null;
      this.__tempLinkNodeId = null;
      this.__tempLinkPortId = null;
      this.__pointerPosX = null;
      this.__pointerPosY = null;
    },

    __getLinkPoints: function(node1, port1, node2, port2) {
      let p1 = null;
      let p2 = null;
      // swap node-ports to have node1 as input and node2 as output
      if (port1.isInput) {
        [node1, port1, node2, port2] = [node2, port2, node1, port1];
      }
      p1 = node1.getLinkPoint(port1);
      p2 = node2.getLinkPoint(port2);
      // hack to place the arrow-head properly
      p2[0] -= 6;
      return [p1, p2];
    },

    __getNode: function(id) {
      for (let i = 0; i < this.__nodes.length; i++) {
        if (this.__nodes[i].getNodeId() === id) {
          return this.__nodes[i];
        }
      }
      for (let nodeUuid in this.__nodeMap) {
        if (id === nodeUuid) {
          return this.__nodeMap[nodeUuid];
        }
      }
      return null;
    },

    __getConnectedLinks: function(nodeId) {
      let connectedLinks = [];
      for (let i = 0; i < this.__links.length; i++) {
        if (this.__links[i].getInputNodeId() === nodeId) {
          connectedLinks.push(this.__links[i].getLinkId());
        }
        if (this.__links[i].getOutputNodeId() === nodeId) {
          connectedLinks.push(this.__links[i].getLinkId());
        }
      }
      return connectedLinks;
    },

    __getLink: function(id) {
      for (let i = 0; i < this.__links.length; i++) {
        if (this.__links[i].getLinkId() === id) {
          return this.__links[i];
        }
      }
      return null;
    },

    __removeNode: function(node) {
      const imageId = node.getNodeImageId();
      if (imageId.includes("dynamic")) {
        const slotName = "stopDynamic";
        let socket = qxapp.wrappers.WebSocket.getInstance();
        let data = {
          nodeId: node.getNodeId()
        };
        socket.emit(slotName, data);
      }

      this.__desktop.remove(node);
      let index = this.__nodes.indexOf(node);
      if (index > -1) {
        this.__nodes.splice(index, 1);
      }
    },

    __removeAllNodes: function() {
      while (this.__nodes.length > 0) {
        this.__removeNode(this.__nodes[this.__nodes.length-1]);
      }
    },

    __removeLink: function(link) {
      let node2 = this.__getNode(link.getOutputNodeId());
      if (node2) {
        node2.getPropsWidget().enableProp(link.getOutputPortId(), true);
      }

      this.__svgWidget.removeCurve(link.getRepresentation());
      let index = this.__links.indexOf(link);
      if (index > -1) {
        this.__links.splice(index, 1);
      }
    },

    __removeAllLinks: function() {
      while (this.__links.length > 0) {
        this.__removeLink(this.__links[this.__links.length-1]);
      }
    },

    removeAll: function() {
      this.__removeAllNodes();
      this.__removeAllLinks();
    },

    __serializeData: function() {
      let pipeline = {
        "nodes": [],
        "links": []
      };
      for (let i = 0; i < this.__nodes.length; i++) {
        let node = {};
        node["uuid"] = this.__nodes[i].getNodeId();
        node["key"] = this.__nodes[i].getMetaData().key;
        node["tag"] = this.__nodes[i].getMetaData().tag;
        node["name"] = this.__nodes[i].getMetaData().name;
        node["inputs"] = this.__nodes[i].getMetaData().inputs;
        node["outputs"] = this.__nodes[i].getMetaData().outputs;
        node["settings"] = this.__nodes[i].getMetaData().settings;
        pipeline["nodes"].push(node);
      }
      for (let i = 0; i < this.__links.length; i++) {
        let link = {};
        link["uuid"] = this.__links[i].getLinkId();
        link["node1Id"] = this.__links[i].getInputNodeId();
        link["port1Id"] = this.__links[i].getInputPortId();
        link["node2Id"] = this.__links[i].getOutputNodeId();
        link["port2Id"] = this.__links[i].getOutputPortId();
        pipeline["links"].push(link);
      }
      return pipeline;
    },

    __loadProject: function(workbenchData) {
      for (let nodeUuid in workbenchData) {
        let nodeData = workbenchData[nodeUuid];
        let node = this.__nodeMap[nodeUuid] =
          this.__createNode(nodeData.key + "-" + nodeData.version, nodeUuid, nodeData);
        this.__addNodeToWorkbench(node, nodeData.position);
      }
      for (let nodeUuid in workbenchData) {
        let nodeData = workbenchData[nodeUuid];
        if (nodeData.inputs) {
          for (let prop in nodeData.inputs) {
            let link = nodeData.inputs[prop];
            if (typeof link == "object" && link.nodeUuid) {
              this.__addLink({
                nodeUuid: link.nodeUuid,
                output: link.output
              }, {
                nodeUuid: nodeUuid,
                input: prop
              });
            }
          }
        }
      }
    },

    addWindowToDesktop: function(node) {
      this.__desktop.add(node);
      node.open();
    },

    __startPipeline: function() {
      // ui start pipeline
      // this.__clearProgressData();

      let socket = qxapp.wrappers.WebSocket.getInstance();

      // callback for incoming logs
      if (!socket.slotExists("logger")) {
        socket.on("logger", function(data) {
          var d = JSON.parse(data);
          var node = d["Node"];
          var msg = d["Message"];
          this.__updateLogger(node, msg);
        }, this);
      }
      socket.emit("logger");

      // callback for incoming progress
      if (!socket.slotExists("progress")) {
        socket.on("progress", function(data) {
          console.log("progress", data);
          var d = JSON.parse(data);
          var node = d["Node"];
          var progress = 100*Number.parseFloat(d["Progress"]).toFixed(4);
          this.updateProgress(node, progress);
        }, this);
      }

      // post pipeline
      this.__pipelineId = null;
      let currentPipeline = this.__serializeData();
      console.log(currentPipeline);
      let req = new qx.io.request.Xhr();
      let data = {};
      data = currentPipeline;
      data["pipeline_mockup_id"] = qxapp.utils.Utils.uuidv4();
      req.set({
        url: "/start_pipeline",
        method: "POST",
        requestData: qx.util.Serializer.toJson(data)
      });
      req.addListener("success", this.__onPipelinesubmitted, this);
      req.addListener("error", function(e) {
        this.setCanStart(true);
        this.__logger.error("Workbench", "Error submitting pipeline");
      }, this);
      req.addListener("fail", function(e) {
        this.setCanStart(true);
        this.__logger.error("Workbench", "Failed submitting pipeline");
      }, this);
      req.send();

      this.__logger.info("Workbench", "Starting pipeline");
    },

    __onPipelinesubmitted: function(e) {
      let req = e.getTarget();
      console.debug("Everything went fine!!");
      console.debug("status  : ", req.getStatus());
      console.debug("phase   : ", req.getPhase());
      console.debug("response: ", req.getResponse());

      const pipelineId = req.getResponse().pipeline_id;
      this.__logger.debug("Workbench", "Pipeline ID " + pipelineId);
      const notGood = [null, undefined, -1];
      if (notGood.includes(pipelineId)) {
        this.setCanStart(true);
        this.__pipelineId = null;
        this.__logger.error("Workbench", "Submition failed");
      } else {
        this.setCanStart(false);
        this.__pipelineId = pipelineId;
        this.__logger.info("Workbench", "Pipeline started");
      }
    },

    __stopPipeline: function() {
      let req = new qx.io.request.Xhr();
      let data = {};
      data["pipeline_id"] = this.__pipelineId;
      req.set({
        url: "/stop_pipeline",
        method: "POST",
        requestData: qx.util.Serializer.toJson(data)
      });
      req.addListener("success", this.__onPipelineStopped, this);
      req.addListener("error", function(e) {
        this.setCanStart(false);
        this.__logger.error("Workbench", "Error stopping pipeline");
      }, this);
      req.addListener("fail", function(e) {
        this.setCanStart(false);
        this.__logger.error("Workbench", "Failed stopping pipeline");
      }, this);
      // req.send();

      // temporary solution
      this.setCanStart(true);

      this.__logger.info("Workbench", "Stopping pipeline. Not yet implemented");
    },

    __onPipelineStopped: function(e) {
      this.__clearProgressData();

      this.setCanStart(true);
    },

    __updateLogger: function(nodeId, msg) {
      let node = this.__getNode(nodeId);
      if (node) {
        this.__logger.info(node.getCaption(), msg);
      }
    },

    __clearProgressData: function() {
      for (let i = 0; i < this.__nodes.length; i++) {
        this.__nodes[i].setProgress(0);
      }
    },

    updateProgress: function(nodeId, progress) {
      let node = this.__getNode(nodeId);
      node.setProgress(progress);
    },

    __selectedItemChanged: function(newID) {
      if (newID === this.__selectedItemId) {
        return;
      }

      let oldId = this.__selectedItemId;
      if (oldId) {
        if (this.__isSelectedItemALink(oldId)) {
          let unselectedLink = this.__getLink(oldId);
          const unselectedColor = qxapp.theme.Color.colors["workbench-link-active"];
          this.__svgWidget.updateColor(unselectedLink.getRepresentation(), unselectedColor);
        }
      }

      this.__selectedItemId = newID;
      if (this.__isSelectedItemALink(newID)) {
        let selectedLink = this.__getLink(newID);
        const selectedColor = qxapp.theme.Color.colors["workbench-link-selected"];
        this.__svgWidget.updateColor(selectedLink.getRepresentation(), selectedColor);
      }
    },

    __isSelectedItemALink: function() {
      return Boolean(this.__getLink(this.__selectedItemId));
    },

    __getProducers: function() {
      const producers = qxapp.dev.fake.Data.getProducers();
      return this.__createMenuFromList(producers);
    },

    __getComputationals: function() {
      const computationals = qxapp.dev.fake.Data.getComputationals();
      return this.__createMenuFromList(computationals);
    },

    __getAnalyses: function() {
      const analyses = qxapp.dev.fake.Data.getAnalyses();
      return this.__createMenuFromList(analyses);
    }
  }
});
