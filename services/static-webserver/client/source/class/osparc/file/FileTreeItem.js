/* ************************************************************************

   osparc - the simcore frontend

   https://osparc.io

   Copyright:
     2019 IT'IS Foundation, https://itis.swiss

   License:
     MIT: https://opensource.org/licenses/MIT

   Authors:
     * Tobias Oetiker (oetiker)
     * Odei Maiz (odeimaiz)

************************************************************************ */

/**
 * VirtualTreeItem used by FilesTree
 *
 *   It consists of an entry icon, label, size, path/location and uuid that can be set through props
 *
 * *Example*
 *
 * Here is a little example of how to use the widget.
 *
 * <pre class='javascript'>
 *   tree.setDelegate({
 *     createItem: () => new osparc.file.FileTreeItem(),
 *     bindItem: (c, item, id) => {
 *       c.bindDefaultProperties(item, id);
 *       c.bindProperty("fileId", "fileId", null, item, id);
 *       c.bindProperty("location", "location", null, item, id);
 *       c.bindProperty("path", "path", null, item, id);
 *       c.bindProperty("size", "size", null, item, id);
 *     }
 *   });
 * </pre>
 */

qx.Class.define("osparc.file.FileTreeItem", {
  extend: qx.ui.tree.VirtualTreeItem,

  construct: function() {
    this.base(arguments);

    this.set({
      indent: 12, // defaults to 19,
      decorator: "rounded",
      alignY: "middle",
    });
  },

  properties: {
    loaded: {
      check: "Boolean",
      event: "changeLoaded",
      init: true,
      nullable: false
    },

    location: {
      check: "String",
      event: "changeLocation",
      nullable: true
    },

    path: {
      check: "String",
      event: "changePath",
      nullable: true
    },

    displayPath: {
      check: "String",
      event: "changeDisplayPath",
      nullable: true
    },

    pathLabel: {
      check: "Array",
      event: "changePathLabel",
      nullable: true
    },

    itemId: {
      check: "String",
      event: "changeItemId",
      apply: "__applyItemId",
      nullable: true
    },

    datasetId: {
      check: "String",
      event: "changeDatasetId",
      nullable: true
    },

    fileId: {
      check: "String",
      event: "changeFileId",
      nullable: true
    },

    lastModified: {
      check: "String",
      event: "changeLastModified",
      nullable: true
    },

    size: {
      check: "String",
      event: "changeSize",
      nullable: true
    },

    type: {
      check: ["folder", "file", "loading"],
      event: "changeType",
      init: null,
      nullable: false,
    },
  },

  members: {
    // overridden
    _addWidgets: function() {
      // Here's our indentation and tree-lines
      this.addSpacer();
      this.addOpenButton();

      // The standard tree icon follows
      this.addIcon();

      // The label
      this.addLabel();

      // All else should be right justified
      this.addWidget(new qx.ui.core.Spacer(), {
        flex: 1
      });

      // Add lastModified
      const lastModifiedWidget = new qx.ui.basic.Label().set({
        maxWidth: 140,
        textAlign: "right",
        alignY: "middle",
        paddingLeft: 10,
      });
      this.bind("lastModified", lastModifiedWidget, "value", {
        converter: value => value ? osparc.utils.Utils.formatDateAndTime(new Date(value)) : ""
      });
      this.addWidget(lastModifiedWidget);

      // Add size
      const sizeWidget = new qx.ui.basic.Label().set({
        maxWidth: 90,
        textAlign: "right",
        alignY: "middle",
        paddingLeft: 10,
      });
      this.bind("size", sizeWidget, "value", {
        converter: value => value ? osparc.utils.Utils.bytesToSize(value) : ""
      });
      this.addWidget(sizeWidget);
    },

    __applyItemId: function(value, old) {
      if (value) {
        osparc.utils.Utils.setIdToWidget(this, "fileTreeItem_" + value);
      }
    },

    // override
    _applyIcon: function(value, old) {
      this.base(arguments, value, old);
      const icon = this.getChildControl("icon", true);
      if (icon && value === "@FontAwesome5Solid/circle-notch/12") {
        icon.setPadding(0);
        icon.setMarginRight(4);
        icon.getContentElement().addClass("rotate");
      } else {
        icon.resetPadding();
        icon.resetMargin();
        icon.getContentElement().removeClass("rotate");
      }
    }
  },
});
