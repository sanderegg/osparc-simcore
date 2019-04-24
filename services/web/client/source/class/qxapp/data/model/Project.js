/* ************************************************************************

   qxapp - the simcore frontend

   https://osparc.io

   Copyright:
     2018 IT'IS Foundation, https://itis.swiss

   License:
     MIT: https://opensource.org/licenses/MIT

   Authors:
     * Odei Maiz (odeimaiz)

************************************************************************ */

/**
 * Class that stores Project/Study data. It is also able to serialize itself.
 *
 *                                    -> {NODES}
 * PROJECT -> METADATA + WORKBENCH ->|
 *                                    -> {LINKS}
 *
 * *Example*
 *
 * Here is a little example of how to use the widget.
 *
 * <pre class='javascript'>
 *   let project = new qxapp.data.model.Project(projectData);
 *   let prjEditor = new qxapp.desktop.PrjEditor(project, isNew);
 * </pre>
 */

qx.Class.define("qxapp.data.model.Project", {
  extend: qx.core.Object,

  /**
    * @param prjData {Object} Object containing the serialized Project Data
    */
  construct: function(prjData) {
    this.base(arguments);

    const wbData = prjData.workbench ? prjData.workbench : {};
    this.set({
      uuid: prjData.uuid || this.getUuid(),
      name: prjData.name || this.getName(),
      description: prjData.description || this.getDescription(),
      notes: prjData.notes || this.getNotes(),
      thumbnail: prjData.thumbnail || this.getThumbnail(),
      prjOwner: prjData.prjOwner || qxapp.auth.Data.getInstance().getUserName(),
      collaborators: prjData.collaborators || this.getCollaborators(),
      creationDate: prjData.creationDate ? new Date(prjData.creationDate) : this.getCreationDate(),
      lastChangeDate: prjData.lastChangeDate ? new Date(prjData.lastChangeDate) : this.getLastChangeDate(),
      workbench: new qxapp.data.model.Workbench(this, wbData)
    });
  },

  properties: {
    uuid: {
      check: "String",
      nullable: false,
      init: qxapp.utils.Utils.uuidv4()
    },

    name: {
      check: "String",
      nullable: false,
      init: "New Project",
      event: "changeName",
      apply : "__applyName"
    },

    description: {
      check: "String",
      nullable: true,
      init: ""
    },

    notes: {
      check: "String",
      nullable: true,
      init: ""
    },

    thumbnail: {
      check: "String",
      nullable: true,
      init: ""
    },

    prjOwner: {
      check: "String",
      nullable: true,
      init: ""
    },

    collaborators: {
      check: "Object",
      nullable: true,
      init: {}
    },

    creationDate: {
      check: "Date",
      nullable: true,
      init: new Date()
    },

    lastChangeDate: {
      check: "Date",
      nullable: true,
      init: new Date()
    },

    workbench: {
      check: "qxapp.data.model.Workbench",
      nullable: false
    }
  },

  members: {
    __applyName: function(newName) {
      if (this.isPropertyInitialized("workbench")) {
        this.getWorkbench().setProjectName(newName);
      }
    },

    serializeProject: function() {
      this.setLastChangeDate(new Date());

      let jsonObject = {};
      let properties = this.constructor.$$properties;
      for (let key in properties) {
        let value = key === "workbench" ? this.getWorkbench().serializeWorkbench() : this.get(key);
        if (value !== null) {
          // only put the value in the payload if there is a value
          jsonObject[key] = value;
        }
      }
      return jsonObject;
    }
  }
});
